"""live.html 에 현재 스냅샷을 심어 단일 HTML 파일로 저장한다.

결과 파일은 열자마자 스냅샷을 보여주고, 브라우저에서 거래소 API 를 직접 호출해 계속 갱신한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models import Snapshot

TEMPLATE = Path(__file__).parent / "dashboard" / "static" / "live.html"
PLACEHOLDER = "/*SNAPSHOT*/null/*END*/"


def render_standalone(snapshot: Snapshot, highlight_pct: float, full_document: bool = True) -> str:
    payload = json.dumps({"snapshot": snapshot.to_dict(), "highlight_pct": highlight_pct}, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")   # </script> 로 스크립트가 끊기지 않게
    body = TEMPLATE.read_text(encoding="utf-8")
    assert body.count(PLACEHOLDER) == 1
    body = body.replace(PLACEHOLDER, payload)
    if not full_document:
        return body
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>'
            + body + "</body></html>")
