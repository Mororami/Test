"""Bitkub 공개 시세 API (인증 불필요)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.exchanges._util import num
from app.models import Ticker

log = logging.getLogger(__name__)

V3_TICKER_URL = "https://api.bitkub.com/api/v3/market/ticker"
LEGACY_TICKER_URL = "https://api.bitkub.com/api/market/ticker"
QUOTE = "THB"

# v3: [{"symbol": "BTC_THB", "last": "...", "percent_change": "...", ...}]
V3_KEYS = dict(last="last", change="percent_change", quote_volume="quote_volume",
               high="high_24_hr", low="low_24_hr", bid="highest_bid", ask="lowest_ask")
# 구버전: {"THB_BTC": {"last": 1.0, "percentChange": 1.0, ...}}
LEGACY_KEYS = dict(last="last", change="percentChange", quote_volume="quoteVolume",
                   high="high24hr", low="low24hr", bid="highestBid", ask="lowestAsk")


def _ticker(base: str, item: dict[str, Any], keys: dict[str, str]) -> Ticker | None:
    last = num(item.get(keys["last"]))
    if last is None or last <= 0:
        return None
    return Ticker(
        symbol=base,
        last=last,
        change_24h_pct=num(item.get(keys["change"])),
        quote_volume_24h=num(item.get(keys["quote_volume"])),
        high_24h=num(item.get(keys["high"])),
        low_24h=num(item.get(keys["low"])),
        bid=num(item.get(keys["bid"])),
        ask=num(item.get(keys["ask"])),
    )


def parse_tickers(payload: Any) -> dict[str, Ticker]:
    """v3(리스트) 와 구버전(딕셔너리) 응답을 모두 {심볼: Ticker} 로 바꾼다."""
    out: dict[str, Ticker] = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            base, _, quote = str(item.get("symbol", "")).upper().partition("_")
            if quote != QUOTE or not base:
                continue
            ticker = _ticker(base, item, V3_KEYS)
            if ticker:
                out[base] = ticker
    elif isinstance(payload, dict):
        for symbol, item in payload.items():
            if not isinstance(item, dict):
                continue
            quote, _, base = str(symbol).upper().partition("_")
            if quote != QUOTE or not base:
                continue
            ticker = _ticker(base, item, LEGACY_KEYS)
            if ticker:
                out[base] = ticker
    else:
        raise ValueError("Bitkub 응답 형식을 알 수 없습니다")
    return out


class BitkubClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_tickers(self) -> dict[str, Ticker]:
        """THB 마켓 전체 시세. v3 가 실패하면 구버전 엔드포인트로 재시도한다."""
        try:
            tickers = parse_tickers(await self._get(V3_TICKER_URL))
            if tickers:
                return tickers
            log.warning("Bitkub v3 응답이 비어 있어 구버전 API 로 재시도합니다")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Bitkub v3 조회 실패(%s), 구버전 API 로 재시도합니다", exc)
        return parse_tickers(await self._get(LEGACY_TICKER_URL))

    async def _get(self, url: str) -> Any:
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()
