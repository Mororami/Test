import pytest

from app.config import config_from_dict
from app.history import PriceHistory
from app.market import build_snapshot, choose_rate, kimp_pct, usdt_implied_rate
from tests.conftest import fx, ticker


def _bitkub():
    return {"BTC": ticker("BTC", 2500000, 1.5, 2e8), "XRP": ticker("XRP", 100, -2, 5e6),
            "USDT": ticker("USDT", 33.25), "ONLYBK": ticker("ONLYBK", 1.5), "EDGE": ticker("EDGE", 10)}


def _bithumb():
    return {"BTC": ticker("BTC", 105000000, 2.0, 3e10), "XRP": ticker("XRP", 4400, -1, 5e8),
            "USDT": ticker("USDT", 1380), "EDGE": ticker("EDGE", 40)}


def test_kimp_and_rows(cfg):
    snap = build_snapshot(bitkub=_bitkub(), bithumb=_bithumb(), forex=fx(41.5), cfg=cfg, now=1000)
    rows = {r.symbol: r for r in snap.rows}
    btc = rows["BTC"]
    assert btc.bitkub_krw == pytest.approx(2500000 * 41.5)
    assert btc.kimp_pct == pytest.approx(kimp_pct(105000000, 2500000 * 41.5))
    assert btc.kimp_pct == pytest.approx((105000000 / 103750000 - 1) * 100)
    assert btc.bithumb_change_24h_pct == 2.0 and btc.bithumb_volume_krw == 3e10
    assert rows["ONLYBK"].bithumb_krw is None and rows["ONLYBK"].kimp_pct is None
    assert snap.rate_used.source == "frankfurter"
    assert snap.usdt_implied_thb_krw == pytest.approx(1380 / 33.25)
    assert snap.stats.bitkub_count == 5 and snap.stats.bithumb_count == 4


def test_suspect_mismatch_excluded_from_stats(cfg):
    snap = build_snapshot(bitkub=_bitkub(), bithumb=_bithumb(), forex=fx(41.5), cfg=cfg, now=1000)
    rows = {r.symbol: r for r in snap.rows}
    assert rows["EDGE"].suspect and rows["EDGE"].kimp_pct == pytest.approx((40 / 415 - 1) * 100)
    assert not rows["BTC"].suspect
    assert snap.stats.matched_count == 3
    assert snap.stats.min_kimp_symbol != "EDGE"


def test_usdt_mode_and_fallbacks(cfg):
    cfg.fx.mode = "usdt"
    snap = build_snapshot(bitkub=_bitkub(), bithumb=_bithumb(), forex=fx(41.5), cfg=cfg, now=1000)
    assert snap.rate_used.source == "usdt_implied" and snap.rate_used.thb_krw == pytest.approx(1380 / 33.25)
    assert snap.forex.thb_krw == 41.5

    # USDT 시세가 없으면 외환으로, 외환도 없으면 오류
    bitkub = _bitkub(); bitkub.pop("USDT")
    assert build_snapshot(bitkub=bitkub, bithumb=_bithumb(), forex=fx(41.5), cfg=cfg, now=1).rate_used.source == "frankfurter"
    with pytest.raises(ValueError):
        build_snapshot(bitkub=bitkub, bithumb=_bithumb(), forex=None, cfg=cfg, now=1)

    cfg.fx.mode = "forex"
    assert build_snapshot(bitkub=_bitkub(), bithumb=_bithumb(), forex=None, cfg=cfg, now=1).rate_used.source == "usdt_implied"


def test_choose_rate_helpers():
    assert usdt_implied_rate({}, {}) is None
    assert choose_rate("forex", None, None, 0) is None


def test_include_exclude_aliases():
    cfg = config_from_dict({"symbols": {"include": ["btc", "xrp"], "exclude": ["xrp"], "aliases": {"btc": "BTCX"}}}, env={})
    bithumb = {"BTCX": ticker("BTCX", 105000000)}
    snap = build_snapshot(bitkub=_bitkub(), bithumb=bithumb, forex=fx(41.5), cfg=cfg, now=1)
    assert [r.symbol for r in snap.rows] == ["BTC"]
    assert snap.rows[0].bithumb_krw == 105000000


def test_short_change_from_history(cfg):
    history = PriceHistory(3600)
    history.record({"XRP": 90}, ts=1000 - 300)
    history.record({"XRP": 100}, ts=1000)
    snap = build_snapshot(bitkub=_bitkub(), bithumb=_bithumb(), forex=fx(), cfg=cfg, history=history, now=1000)
    rows = {r.symbol: r for r in snap.rows}
    assert rows["XRP"].change_short_pct == pytest.approx(100 / 90 * 100 - 100)
    assert rows["BTC"].change_short_pct is None
    assert snap.short_window_min == 5


def test_median_stats(cfg):
    snap = build_snapshot(bitkub=_bitkub(), bithumb=_bithumb(), forex=fx(41.5), cfg=cfg, now=1)
    kimps = sorted(r.kimp_pct for r in snap.rows if r.kimp_pct is not None and not r.suspect)
    assert snap.stats.median_kimp_pct == pytest.approx(kimps[1])
    assert snap.stats.max_kimp_pct == pytest.approx(kimps[-1])
    d = snap.to_dict()
    assert d["rows"][0]["symbol"] == "BTC" and d["rate_used"]["thb_krw"] == 41.5
