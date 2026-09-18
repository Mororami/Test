import httpx
import pytest

from app.collector import Collector
from app.config import config_from_dict
from tests.conftest import default_handler, json_response


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


async def test_poll_builds_snapshot_and_sends_alerts():
    cfg = config_from_dict({"alerts": {"kimp": {"threshold_pct": 0.5, "min_quote_volume_thb": 0, "min_quote_volume_krw": 0}}}, env={})
    notifier = FakeNotifier()
    async with Collector(cfg, alerts_enabled=True, notifier=notifier,
                         transport=httpx.MockTransport(default_handler)) as c:
        snap = await c.poll_once(now=1000)
        assert snap is not None and c.last_error is None and c.polls == 1
        rows = {r.symbol: r for r in snap.rows}
        assert rows["BTC"].kimp_pct == pytest.approx((105000000 / (2500000 * 41.5) - 1) * 100)
        assert snap.rate_used.source == "frankfurter" and snap.usdt_implied_thb_krw == pytest.approx(1380 / 33.25)
        assert len(c.history) == 4                       # Bitkub THB 마켓 4개 기록
        kinds = {(a.kind, a.symbol) for a in c.recent_alerts}
        assert ("kimp", "BTC") in kinds and ("kimp", "XRP") in kinds
        assert len(notifier.sent) == 1 and "BTC 김프" in notifier.sent[0] and "XRP 김프" in notifier.sent[0]

        # 두 번째 폴링: 같은 조건이 유지되므로 재알림 없음
        await c.poll_once(now=1030)
        assert len(notifier.sent) == 1 and c.polls == 2


async def test_alerts_evaluated_but_not_sent_when_disabled():
    cfg = config_from_dict({"alerts": {"kimp": {"threshold_pct": 0.5, "min_quote_volume_thb": 0, "min_quote_volume_krw": 0}}}, env={})
    notifier = FakeNotifier()
    async with Collector(cfg, alerts_enabled=False, notifier=notifier, transport=httpx.MockTransport(default_handler)) as c:
        await c.poll_once(now=1000)
    assert c.recent_alerts and notifier.sent == []


async def test_bithumb_failure_uses_cache_and_marks_stale():
    state = {"fail": False}

    def handler(request):
        if request.url.host == "api.bithumb.com" and state["fail"]:
            return httpx.Response(500)
        return default_handler(request)

    cfg = config_from_dict({}, env={})
    async with Collector(cfg, transport=httpx.MockTransport(handler)) as c:
        first = await c.poll_once(now=1000)
        assert first.bithumb_stale_sec is None
        state["fail"] = True
        second = await c.poll_once(now=1090)
        assert second is not None and second.bithumb_stale_sec == pytest.approx(90)
        assert {r.symbol: r for r in second.rows}["BTC"].bithumb_krw == 105000000


async def test_bitkub_failure_sets_error_keeps_last_snapshot():
    state = {"fail": False}

    def handler(request):
        if request.url.host == "api.bitkub.com" and state["fail"]:
            return httpx.Response(502)
        return default_handler(request)

    async with Collector(config_from_dict({}, env={}), transport=httpx.MockTransport(handler)) as c:
        first = await c.poll_once(now=1000)
        state["fail"] = True
        assert await c.poll_once(now=1030) is None
        assert c.snapshot is first and "Bitkub" in c.last_error
        assert c.status()["polls"] == 1


async def test_fx_failure_falls_back_to_usdt_implied():
    def handler(request):
        if request.url.host in ("api.frankfurter.dev", "open.er-api.com"):
            return httpx.Response(500)
        return default_handler(request)

    async with Collector(config_from_dict({}, env={}), transport=httpx.MockTransport(handler)) as c:
        snap = await c.poll_once(now=1000)
    assert snap.forex is None and snap.rate_used.source == "usdt_implied"


async def test_notifier_failure_does_not_break_polling():
    class Broken:
        async def send(self, text):
            raise RuntimeError("telegram down")

    cfg = config_from_dict({"alerts": {"kimp": {"threshold_pct": 0.5, "min_quote_volume_thb": 0, "min_quote_volume_krw": 0}}}, env={})
    async with Collector(cfg, alerts_enabled=True, notifier=Broken(), transport=httpx.MockTransport(default_handler)) as c:
        assert await c.poll_once(now=1000) is not None
        assert c.last_error is None
