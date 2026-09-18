"""주기적으로 시세·환율을 모아 스냅샷을 만들고, 알림을 판정·발송한다. 봇과 대시보드가 공유한다."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

import httpx

from app.alerts import AlertEngine, format_startup
from app.config import AppConfig
from app.exchanges import BithumbClient, BitkubClient, FxClient
from app.history import PriceHistory
from app.market import build_snapshot
from app.models import Alert, Snapshot, Ticker
from app.notifier import Notifier, build_notifier

log = logging.getLogger(__name__)

USER_AGENT = "kimp-monitor/1.0 (+https://github.com/mororami/test)"
HTTP_TIMEOUT = httpx.Timeout(15.0)


class Collector:
    def __init__(self, cfg: AppConfig, *, alerts_enabled: bool = False,
                 notifier: Notifier | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.cfg = cfg
        self._transport = transport   # 테스트에서 MockTransport 주입용
        self.alerts_enabled = alerts_enabled
        self.notifier = notifier
        self.history = PriceHistory(cfg.history_max_age_sec)
        self.engine = AlertEngine(cfg.alerts)
        self.recent_alerts: deque[Alert] = deque(maxlen=200)
        self.snapshot: Snapshot | None = None
        self.last_error: str | None = None
        self.last_success_ts: float | None = None
        self.polls = 0
        self._client: httpx.AsyncClient | None = None
        self._bitkub: BitkubClient | None = None
        self._bithumb: BithumbClient | None = None
        self._fx: FxClient | None = None
        self._bithumb_cache: tuple[dict[str, Ticker], float] | None = None

    # ---- 수명 주기 -------------------------------------------------------
    async def start(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT},
                                         transport=self._transport)
        self._bitkub = BitkubClient(self._client)
        self._bithumb = BithumbClient(self._client)
        self._fx = FxClient(self._client, refresh_sec=self.cfg.fx.refresh_sec,
                            override=self.cfg.fx.override_thb_krw)
        if self.alerts_enabled and self.notifier is None:
            self.notifier = build_notifier(self.cfg, self._client)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "Collector":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ---- 한 사이클 -------------------------------------------------------
    async def poll_once(self, now: float | None = None) -> Snapshot | None:
        """시세·환율을 모아 스냅샷을 만든다. 실패하면 None 을 돌려주고 last_error 에 이유를 남긴다."""
        if self._client is None:
            await self.start()
        assert self._bitkub and self._bithumb and self._fx
        now = time.time() if now is None else now

        bitkub_res, bithumb_res, fx_res = await asyncio.gather(
            self._bitkub.fetch_tickers(),
            self._bithumb.fetch_tickers(),
            self._fx.get_thb_krw(now),
            return_exceptions=True,
        )
        if isinstance(bitkub_res, BaseException):
            return self._fail(f"Bitkub 조회 실패: {bitkub_res!r}")
        bitkub = bitkub_res

        stale: float | None = None
        if isinstance(bithumb_res, BaseException):
            log.warning("Bithumb 조회 실패, 이전 데이터 사용: %r", bithumb_res)
            if self._bithumb_cache is None:
                bithumb: dict[str, Ticker] = {}
            else:
                bithumb, cached_at = self._bithumb_cache
                stale = now - cached_at
        else:
            bithumb = bithumb_res
            self._bithumb_cache = (bithumb, now)

        forex = None
        if isinstance(fx_res, BaseException):
            log.warning("환율 조회 실패: %r", fx_res)
        else:
            forex = fx_res

        self.history.record({sym: t.last for sym, t in bitkub.items()}, now)
        try:
            snapshot = build_snapshot(bitkub=bitkub, bithumb=bithumb, forex=forex, cfg=self.cfg,
                                      history=self.history, now=now, bithumb_stale_sec=stale)
        except ValueError as exc:
            return self._fail(str(exc))

        self.snapshot = snapshot
        self.last_success_ts = now
        self.last_error = None
        self.polls += 1
        log.info("수집 #%d: Bitkub %d, Bithumb %d, 비교 %d, 환율 %.3f(%s), 김프 중간값 %s",
                 self.polls, snapshot.stats.bitkub_count, snapshot.stats.bithumb_count,
                 snapshot.stats.matched_count, snapshot.rate_used.thb_krw, snapshot.rate_used.source,
                 "-" if snapshot.stats.median_kimp_pct is None else f"{snapshot.stats.median_kimp_pct:+.2f}%")

        alerts = self.engine.evaluate(snapshot, now)
        if alerts:
            self.recent_alerts.extend(alerts)
            await self._notify(alerts)
        return snapshot

    def _fail(self, message: str) -> None:
        self.last_error = message
        log.error("%s", message)
        return None

    async def _notify(self, alerts: list[Alert]) -> None:
        for alert in alerts:
            log.info("알림 [%s] %s %+.2f%%", alert.kind, alert.symbol, alert.value)
        if not self.alerts_enabled or self.notifier is None:
            return
        try:
            await self.notifier.send("\n\n".join(a.text for a in alerts))
        except Exception as exc:  # 전송 실패가 수집 루프를 죽이면 안 된다
            log.error("알림 전송 실패: %r", exc)

    # ---- 루프 ------------------------------------------------------------
    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        await self.start()
        if self.alerts_enabled and self.notifier is not None and self.cfg.alerts.startup_message:
            try:
                await self.notifier.send(format_startup(self.cfg.poll_interval_sec, self.cfg.alerts))
            except Exception as exc:
                log.error("시작 알림 전송 실패: %r", exc)
        while not stop.is_set():
            started = time.monotonic()
            try:
                await self.poll_once()
            except Exception:
                log.exception("수집 중 예기치 않은 오류")
            delay = max(0.0, self.cfg.poll_interval_sec - (time.monotonic() - started))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    def status(self) -> dict[str, Any]:
        return {
            "polls": self.polls,
            "last_success_ts": self.last_success_ts,
            "last_error": self.last_error,
            "alerts_enabled": self.alerts_enabled,
            "telegram_configured": self.cfg.telegram.configured,
        }
