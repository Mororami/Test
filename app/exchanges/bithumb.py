"""Bithumb 공개 시세 API v1 (Upbit 호환 형식, 인증 불필요)."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.exchanges._util import num
from app.models import Ticker

log = logging.getLogger(__name__)

MARKETS_URL = "https://api.bithumb.com/v1/market/all"
TICKER_URL = "https://api.bithumb.com/v1/ticker"
QUOTE = "KRW"
CHUNK_SIZE = 100          # ticker 한 번에 조회할 마켓 수
MARKETS_TTL_SEC = 3600    # 마켓 목록 캐시 시간


def parse_markets(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        raise ValueError("Bithumb 마켓 목록 응답 형식을 알 수 없습니다")
    markets = []
    for item in payload:
        market = str(item.get("market", "")) if isinstance(item, dict) else ""
        if market.startswith(f"{QUOTE}-"):
            markets.append(market)
    return markets


def parse_tickers(payload: Any) -> dict[str, Ticker]:
    if not isinstance(payload, list):
        raise ValueError("Bithumb 시세 응답 형식을 알 수 없습니다")
    out: dict[str, Ticker] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        quote, _, base = str(item.get("market", "")).upper().partition("-")
        if quote != QUOTE or not base:
            continue
        last = num(item.get("trade_price"))
        if last is None or last <= 0:
            continue
        rate = num(item.get("signed_change_rate"))  # 소수 비율 (0.02 = 2%)
        out[base] = Ticker(
            symbol=base,
            last=last,
            change_24h_pct=None if rate is None else rate * 100,
            quote_volume_24h=num(item.get("acc_trade_price_24h")),
            high_24h=num(item.get("high_price")),
            low_24h=num(item.get("low_price")),
        )
    return out


class BithumbClient:
    def __init__(self, client: httpx.AsyncClient, markets_ttl_sec: float = MARKETS_TTL_SEC) -> None:
        self._client = client
        self._markets_ttl = markets_ttl_sec
        self._markets: list[str] | None = None
        self._markets_ts = 0.0

    async def fetch_markets(self, now: float | None = None) -> list[str]:
        """KRW 마켓 코드 목록 (캐시)."""
        now = time.time() if now is None else now
        if self._markets is not None and now - self._markets_ts < self._markets_ttl:
            return self._markets
        response = await self._client.get(MARKETS_URL, params={"isDetails": "false"})
        response.raise_for_status()
        markets = parse_markets(response.json())
        if not markets:
            raise ValueError("Bithumb KRW 마켓이 하나도 없습니다")
        self._markets, self._markets_ts = markets, now
        return markets

    async def fetch_tickers(self) -> dict[str, Ticker]:
        markets = await self.fetch_markets()
        out: dict[str, Ticker] = {}
        for i in range(0, len(markets), CHUNK_SIZE):
            chunk = markets[i:i + CHUNK_SIZE]
            response = await self._client.get(TICKER_URL, params={"markets": ",".join(chunk)})
            response.raise_for_status()
            out.update(parse_tickers(response.json()))
        return out
