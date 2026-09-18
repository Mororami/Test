from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from app.config import AppConfig, config_from_dict
from app.models import FxRate, Ticker

BITKUB_V3 = [
    {"symbol": "BTC_THB", "last": "2500000", "percent_change": "1.5", "quote_volume": "200000000",
     "high_24_hr": "2600000", "low_24_hr": "2400000", "highest_bid": "2499000", "lowest_ask": "2501000"},
    {"symbol": "XRP_THB", "last": "100", "percent_change": "-2", "quote_volume": "5000000",
     "high_24_hr": "105", "low_24_hr": "98", "highest_bid": "99.9", "lowest_ask": "100.1"},
    {"symbol": "USDT_THB", "last": "33.25", "percent_change": "0", "quote_volume": "900000000",
     "high_24_hr": "33.3", "low_24_hr": "33.2", "highest_bid": "33.24", "lowest_ask": "33.26"},
    {"symbol": "ONLYBK_THB", "last": "1.5", "percent_change": "0", "quote_volume": "10000",
     "high_24_hr": "1.6", "low_24_hr": "1.4", "highest_bid": "1.49", "lowest_ask": "1.51"},
    {"symbol": "BTC_USDT", "last": "75000", "percent_change": "1", "quote_volume": "1"},
    {"symbol": "ZERO_THB", "last": "0", "percent_change": "0", "quote_volume": "0"},
]

BITHUMB_MARKETS = [
    {"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"},
    {"market": "KRW-XRP", "korean_name": "엑스알피", "english_name": "XRP"},
    {"market": "KRW-USDT", "korean_name": "테더", "english_name": "Tether"},
    {"market": "BTC-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
]

BITHUMB_TICKERS = [
    {"market": "KRW-BTC", "trade_price": 105000000, "signed_change_rate": 0.02,
     "acc_trade_price_24h": 30000000000, "high_price": 106000000, "low_price": 104000000},
    {"market": "KRW-XRP", "trade_price": 4400, "signed_change_rate": -0.01,
     "acc_trade_price_24h": 500000000, "high_price": 4500, "low_price": 4300},
    {"market": "KRW-USDT", "trade_price": 1380, "signed_change_rate": 0.0,
     "acc_trade_price_24h": 60000000000, "high_price": 1385, "low_price": 1375},
]

FRANKFURTER = {"amount": 1.0, "base": "THB", "date": "2026-09-17", "rates": {"KRW": 41.5}}
ER_API = {"result": "success", "time_last_update_utc": "Fri, 18 Sep 2026 00:02:31 +0000", "rates": {"KRW": 41.49}}


def ticker(symbol: str, last: float, change: float | None = None, volume: float | None = None) -> Ticker:
    return Ticker(symbol=symbol, last=last, change_24h_pct=change, quote_volume_24h=volume)


def fx(rate: float = 41.5, source: str = "frankfurter", at: float = 1000.0) -> FxRate:
    return FxRate(thb_krw=rate, source=source, fetched_at=at, as_of="2026-09-17")


@pytest.fixture
def cfg() -> AppConfig:
    return config_from_dict({}, env={})


def json_response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def default_handler(request: httpx.Request) -> httpx.Response:
    """정상 응답을 주는 기본 핸들러. 테스트에서 특정 호스트만 바꿔 쓴다."""
    host, path = request.url.host, request.url.path
    if host == "api.bitkub.com":
        return json_response(BITKUB_V3)
    if host == "api.bithumb.com" and path == "/v1/market/all":
        return json_response(BITHUMB_MARKETS)
    if host == "api.bithumb.com" and path == "/v1/ticker":
        wanted = set(request.url.params["markets"].split(","))
        return json_response([t for t in BITHUMB_TICKERS if t["market"] in wanted])
    if host == "api.frankfurter.dev":
        return json_response(FRANKFURTER)
    if host == "open.er-api.com":
        return json_response(ER_API)
    return httpx.Response(404, content=b"unknown host")
