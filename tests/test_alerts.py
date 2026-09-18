import pytest

from app.alerts import KIND_CHANGE_24H, KIND_KIMP, KIND_PUMP, AlertEngine, format_alert, format_startup
from app.config import config_from_dict
from app.models import CoinRow, Snapshot, SnapshotStats
from tests.conftest import fx


def snap(rows, now=1000.0):
    return Snapshot(ts=now, rate_used=fx(41.5), forex=fx(41.5), usdt_implied_thb_krw=41.4,
                    rows=rows, stats=SnapshotStats(), short_window_min=5)


def row(symbol="BTC", short=None, c24=None, kimp=None, vol_thb=1e6, vol_krw=1e9, suspect=False):
    return CoinRow(symbol=symbol, bitkub_thb=100, bitkub_krw=4150, bithumb_krw=None if kimp is None else 4150 * (1 + kimp / 100),
                   kimp_pct=kimp, change_short_pct=short, bitkub_change_24h_pct=c24,
                   bitkub_volume_thb=vol_thb, bithumb_volume_krw=vol_krw, suspect=suspect)


def engine(**alerts):
    cfg = config_from_dict({"alerts": alerts} if alerts else {}, env={})
    return AlertEngine(cfg.alerts)


def test_pump_threshold_and_volume():
    e = engine(pump={"threshold_pct": 5, "min_quote_volume_thb": 100000})
    out = e.evaluate(snap([row("A", short=5.0), row("B", short=4.99), row("C", short=9, vol_thb=1000), row("D", short=None)]))
    assert [(a.kind, a.symbol) for a in out] == [(KIND_PUMP, "A")]
    assert out[0].value == 5.0 and "A 급등" in out[0].text and "+5.00%" in out[0].text


def test_edge_trigger_cooldown_and_rearm():
    e = engine(cooldown_min=30, kimp={"enabled": False})
    assert len(e.evaluate(snap([row(short=6)]), now=0)) == 1
    assert e.evaluate(snap([row(short=7)]), now=60) == []            # 계속 충족 중이면 다시 알리지 않음
    assert e.evaluate(snap([row(short=1)]), now=120) == []           # 조건 해제 → 재무장
    assert e.evaluate(snap([row(short=8)]), now=180) == []           # 재충족했지만 쿨다운 안
    assert e.evaluate(snap([row(short=1)]), now=200) == []
    assert len(e.evaluate(snap([row(short=8)]), now=30 * 60 + 1)) == 1   # 쿨다운 지남


def test_kimp_abs_suspect_and_volumes():
    e = engine(pump={"enabled": False}, kimp={"threshold_pct": 5, "min_quote_volume_thb": 1000, "min_quote_volume_krw": 1000})
    out = e.evaluate(snap([row("NEG", kimp=-6), row("POS", kimp=6), row("SMALL", kimp=4),
                           row("SUS", kimp=80, suspect=True), row("LOWKRW", kimp=9, vol_krw=10),
                           row("UNLISTED", kimp=None)]))
    assert sorted((a.symbol, a.kind) for a in out) == [("NEG", KIND_KIMP), ("POS", KIND_KIMP)]
    neg = next(a for a in out if a.symbol == "NEG")
    assert "🔻" in neg.text and "-6.00%" in neg.text


def test_change_24h_disabled_by_default_and_enabled():
    assert engine().evaluate(snap([row(c24=50)])) == []
    e = engine(change_24h={"enabled": True, "threshold_pct": 20}, pump={"enabled": False}, kimp={"enabled": False})
    out = e.evaluate(snap([row(c24=25)]))
    assert [a.kind for a in out] == [KIND_CHANGE_24H]


def test_multiple_kinds_same_symbol_are_independent():
    e = engine(pump={"threshold_pct": 5}, kimp={"threshold_pct": 5})
    out = e.evaluate(snap([row(short=10, kimp=10)]))
    assert sorted(a.kind for a in out) == [KIND_KIMP, KIND_PUMP]


def test_message_contents():
    text = format_alert(KIND_PUMP, row("XRP", short=7.5, c24=1.2, kimp=2.5), snap([]))
    for piece in ("XRP", "5분 +7.50%", "100.00 THB", "4,150원", "Bithumb:", "김프 +2.50%", "41.500원"):
        assert piece in text
    text = format_alert(KIND_KIMP, row("ONLY", kimp=None), snap([]))
    assert "Bithumb: 미상장" in text
    startup = format_startup(30, config_from_dict({}, env={}).alerts)
    assert "5분 내 +5% 이상" in startup and "|5%| 이상" in startup
