import httpx
import pytest

from app.exchanges.fx import FxClient, FxUnavailable
from tests.conftest import ER_API, FRANKFURTER, json_response, mock_client


async def test_primary_then_cache():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return json_response(FRANKFURTER)

    async with mock_client(handler) as client:
        fx = FxClient(client, refresh_sec=100)
        a = await fx.get_thb_krw(now=0)
        b = await fx.get_thb_krw(now=50)
        c = await fx.get_thb_krw(now=150)
    assert a.thb_krw == 41.5 and a.source == "frankfurter" and a.as_of == "2026-09-17"
    assert b is a                       # 캐시
    assert c is not a and calls == ["api.frankfurter.dev", "api.frankfurter.dev"]


async def test_fallback_source():
    def handler(request):
        if request.url.host == "api.frankfurter.dev":
            return httpx.Response(503)
        return json_response(ER_API)

    async with mock_client(handler) as client:
        rate = await FxClient(client).get_thb_krw(now=0)
    assert rate.thb_krw == 41.49 and rate.source == "exchangerate-api"


async def test_stale_cache_when_all_fail_then_unavailable():
    ok = {"value": True}

    def handler(request):
        return json_response(FRANKFURTER) if ok["value"] else httpx.Response(500)

    async with mock_client(handler) as client:
        fx = FxClient(client, refresh_sec=10)
        first = await fx.get_thb_krw(now=0)
        ok["value"] = False
        stale = await fx.get_thb_krw(now=100)
        assert stale is first

        fresh = FxClient(client)
        with pytest.raises(FxUnavailable):
            await fresh.get_thb_krw(now=0)


async def test_override_skips_network():
    def handler(request):
        raise AssertionError("네트워크를 타면 안 된다")

    async with mock_client(handler) as client:
        rate = await FxClient(client, override=40.0).get_thb_krw(now=5)
    assert rate.thb_krw == 40.0 and rate.source == "override"


async def test_rejects_nonpositive_rate():
    def handler(request):
        if request.url.host == "api.frankfurter.dev":
            return json_response({"rates": {"KRW": 0}})
        return json_response({"result": "error"})

    async with mock_client(handler) as client:
        with pytest.raises(FxUnavailable):
            await FxClient(client).get_thb_krw(now=0)
