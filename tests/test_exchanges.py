import httpx
import pytest

from app.exchanges.bithumb import BithumbClient, parse_markets, parse_tickers as parse_bithumb
from app.exchanges.bitkub import LEGACY_TICKER_URL, V3_TICKER_URL, BitkubClient, parse_tickers as parse_bitkub
from tests.conftest import BITHUMB_MARKETS, BITHUMB_TICKERS, BITKUB_V3, json_response, mock_client


def test_parse_bitkub_v3():
    out = parse_bitkub(BITKUB_V3)
    assert set(out) == {"BTC", "XRP", "USDT", "ONLYBK"}   # BTC_USDT(다른 호가통화)·ZERO(가격 0) 제외
    assert out["BTC"].last == 2500000
    assert out["BTC"].change_24h_pct == 1.5
    assert out["BTC"].quote_volume_24h == 200000000
    assert out["BTC"].bid == 2499000 and out["BTC"].ask == 2501000


def test_parse_bitkub_legacy():
    payload = {"THB_BTC": {"last": 2500000, "percentChange": 1.5, "quoteVolume": 1e8, "high24hr": 1, "low24hr": 1,
                           "highestBid": 1, "lowestAsk": 1},
               "USDT_BTC": {"last": 75000}}
    out = parse_bitkub(payload)
    assert list(out) == ["BTC"] and out["BTC"].change_24h_pct == 1.5


def test_parse_bitkub_bad_shape():
    with pytest.raises(ValueError):
        parse_bitkub("nope")


def test_parse_bithumb():
    assert parse_markets(BITHUMB_MARKETS) == ["KRW-BTC", "KRW-XRP", "KRW-USDT"]
    out = parse_bithumb(BITHUMB_TICKERS)
    assert out["BTC"].last == 105000000
    assert out["BTC"].change_24h_pct == pytest.approx(2.0)    # 소수 비율 → %
    assert out["XRP"].quote_volume_24h == 500000000


async def test_bitkub_falls_back_to_legacy():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == V3_TICKER_URL:
            return httpx.Response(500)
        assert str(request.url) == LEGACY_TICKER_URL
        return json_response({"THB_BTC": {"last": 1, "percentChange": 0, "quoteVolume": 0}})

    async with mock_client(handler) as client:
        out = await BitkubClient(client).fetch_tickers()
    assert list(out) == ["BTC"]
    assert calls == [V3_TICKER_URL, LEGACY_TICKER_URL]


async def test_bithumb_chunks_and_caches_markets():
    markets = [{"market": f"KRW-C{i}"} for i in range(250)]
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/v1/market/all":
            return json_response(markets)
        wanted = request.url.params["markets"].split(",")
        assert len(wanted) <= 100
        return json_response([{"market": m, "trade_price": 1, "signed_change_rate": 0} for m in wanted])

    async with mock_client(handler) as client:
        bh = BithumbClient(client)
        out = await bh.fetch_tickers()
        await bh.fetch_tickers()
    assert len(out) == 250
    assert requests.count("/v1/market/all") == 1      # 두 번째 호출은 캐시
    assert requests.count("/v1/ticker") == 6           # 3 청크 × 2회
