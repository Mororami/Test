import httpx
from fastapi.testclient import TestClient

from app.collector import Collector
from app.config import config_from_dict
from app.dashboard import create_app
from tests.conftest import default_handler


def make_client(with_snapshot: bool = True) -> tuple[TestClient, Collector]:
    cfg = config_from_dict({"alerts": {"kimp": {"threshold_pct": 0.5, "min_quote_volume_thb": 0, "min_quote_volume_krw": 0}}}, env={})
    collector = Collector(cfg, transport=httpx.MockTransport(default_handler))
    app = create_app(collector, cfg, autostart=False)
    client = TestClient(app)
    if with_snapshot:
        import asyncio
        asyncio.run(collector.poll_once(now=1000))
    return client, collector


def test_index_and_snapshot():
    client, collector = make_client()
    with client:
        html = client.get("/")
        assert html.status_code == 200 and "김프 대시보드" in html.text
        data = client.get("/api/snapshot").json()
        assert data["ok"] is True
        assert data["meta"]["poll_interval_sec"] == 30 and data["meta"]["short_window_min"] == 5
        symbols = [r["symbol"] for r in data["snapshot"]["rows"]]
        assert symbols == ["BTC", "ONLYBK", "USDT", "XRP"]
        alerts = client.get("/api/alerts?limit=1").json()["alerts"]
        assert len(alerts) == 1 and alerts[0]["kind"] == "kimp"


def test_health_without_data_is_503():
    client, _ = make_client(with_snapshot=False)
    with client:
        assert client.get("/api/health").status_code == 503
        body = client.get("/api/snapshot").json()
        assert body["ok"] is False and body["snapshot"] is None
