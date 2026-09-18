"""김프 대시보드 웹 서버 (FastAPI). 정적 HTML 한 장 + JSON API."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

from app.collector import Collector
from app.config import AppConfig

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def create_app(collector: Collector, cfg: AppConfig, autostart: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = asyncio.Event()
        task = asyncio.create_task(collector.run(stop)) if autostart else None
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                with contextlib.suppress(Exception):
                    await task
            await collector.close()

    app = FastAPI(title="Bitkub × Bithumb 김프 대시보드", lifespan=lifespan)

    def meta() -> dict[str, Any]:
        return {
            "server_time": time.time(),
            "poll_interval_sec": cfg.poll_interval_sec,
            "kimp_highlight_pct": cfg.dashboard.kimp_highlight_pct,
            "short_window_min": cfg.alerts.pump.window_min,
            "fx_mode": cfg.fx.mode,
            **collector.status(),
        }

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/api/snapshot")
    async def snapshot() -> dict[str, Any]:
        snap = collector.snapshot
        return {"ok": snap is not None, "snapshot": snap.to_dict() if snap else None, "meta": meta()}

    @app.get("/api/alerts")
    async def alerts(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        items = list(collector.recent_alerts)[-limit:]
        items.reverse()
        return {"alerts": [a.to_dict() for a in items]}

    @app.get("/api/health")
    async def health() -> JSONResponse:
        fresh = (collector.last_success_ts is not None
                 and time.time() - collector.last_success_ts < cfg.poll_interval_sec * 4)
        return JSONResponse({"ok": fresh, **collector.status()}, status_code=200 if fresh else 503)

    return app
