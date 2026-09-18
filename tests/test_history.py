import pytest

from app.history import PriceHistory


def test_change_pct_uses_sample_at_window_start():
    h = PriceHistory(max_age_sec=600)
    for i, price in enumerate([100, 101, 102, 110]):
        h.record({"BTC": price}, ts=i * 30)
    # now=90, window 60s → 30초 시점(101) 대비
    assert h.change_pct("BTC", 60, now=90) == pytest.approx((110 / 101 - 1) * 100)


def test_insufficient_history_returns_none():
    h = PriceHistory(max_age_sec=600)
    h.record({"BTC": 100}, ts=0)
    h.record({"BTC": 120}, ts=30)
    assert h.change_pct("BTC", 300, now=30) is None
    assert h.change_pct("BTC", 300, now=30, tolerance_sec=15) is None
    assert h.change_pct("BTC", 300, now=290, tolerance_sec=15) == pytest.approx(20.0)
    assert h.change_pct("ETH", 60, now=30) is None


def test_prune_and_zero_prices():
    h = PriceHistory(max_age_sec=100)
    h.record({"BTC": 1, "BAD": 0}, ts=0)
    h.record({"BTC": 2}, ts=50)
    h.record({"BTC": 3}, ts=150)
    assert "BAD" not in h.series("BTC") and len(h) == 1
    assert [p for _, p in h.series("BTC")] == [2, 3]     # ts=0 샘플은 만료
    assert h.latest("BTC") == (150, 3)
