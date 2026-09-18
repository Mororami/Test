"""Bitkub·Bithumb 시세와 환율을 합쳐 김프 스냅샷을 만든다."""
from __future__ import annotations

import logging
import statistics
import time

from app.config import AppConfig
from app.history import PriceHistory
from app.models import CoinRow, FxRate, Snapshot, SnapshotStats, Ticker

log = logging.getLogger(__name__)

STABLE = "USDT"


def usdt_implied_rate(bitkub: dict[str, Ticker], bithumb: dict[str, Ticker]) -> float | None:
    """양 거래소 USDT 가격으로 역산한 THB→KRW 환율 (KRW/USDT ÷ THB/USDT)."""
    a, b = bitkub.get(STABLE), bithumb.get(STABLE)
    if a is None or b is None or a.last <= 0:
        return None
    return b.last / a.last


def choose_rate(mode: str, forex: FxRate | None, usdt_implied: float | None, now: float) -> FxRate | None:
    """설정된 모드의 환율을 고르되, 없으면 다른 쪽으로 대체한다."""
    implied = None if usdt_implied is None else FxRate(usdt_implied, "usdt_implied", now)
    if mode == "usdt":
        return implied or forex
    return forex or implied


def kimp_pct(bithumb_krw: float, bitkub_krw: float) -> float:
    return (bithumb_krw / bitkub_krw - 1) * 100


def build_snapshot(
    *,
    bitkub: dict[str, Ticker],
    bithumb: dict[str, Ticker],
    forex: FxRate | None,
    cfg: AppConfig,
    history: PriceHistory | None = None,
    now: float | None = None,
    bithumb_stale_sec: float | None = None,
) -> Snapshot:
    now = time.time() if now is None else now
    implied = usdt_implied_rate(bitkub, bithumb)
    rate = choose_rate(cfg.fx.mode, forex, implied, now)
    if rate is None:
        raise ValueError("사용할 수 있는 THB→KRW 환율이 없습니다")

    include = set(cfg.symbols.include)
    exclude = set(cfg.symbols.exclude)
    aliases = cfg.symbols.aliases
    window_sec = cfg.alerts.pump.window_min * 60
    tolerance = cfg.poll_interval_sec / 2

    rows: list[CoinRow] = []
    for base in sorted(bitkub):
        if (include and base not in include) or base in exclude:
            continue
        bt = bitkub[base]
        bh = bithumb.get(aliases.get(base, base))
        bitkub_krw = bt.last * rate.thb_krw
        row = CoinRow(
            symbol=base,
            bitkub_thb=bt.last,
            bitkub_krw=bitkub_krw,
            bitkub_change_24h_pct=bt.change_24h_pct,
            bitkub_volume_thb=bt.quote_volume_24h,
            change_short_pct=history.change_pct(base, window_sec, now, tolerance) if history else None,
        )
        if bh is not None and bitkub_krw > 0:
            row.bithumb_krw = bh.last
            row.kimp_pct = kimp_pct(bh.last, bitkub_krw)
            row.suspect = abs(row.kimp_pct) >= cfg.symbols.mismatch_kimp_pct
            row.bithumb_change_24h_pct = bh.change_24h_pct
            row.bithumb_volume_krw = bh.quote_volume_24h
        rows.append(row)

    return Snapshot(
        ts=now,
        rate_used=rate,
        forex=forex,
        usdt_implied_thb_krw=implied,
        rows=rows,
        stats=compute_stats(rows, len(bitkub), len(bithumb)),
        short_window_min=cfg.alerts.pump.window_min,
        bithumb_stale_sec=bithumb_stale_sec,
    )


def compute_stats(rows: list[CoinRow], bitkub_count: int, bithumb_count: int) -> SnapshotStats:
    matched = [r for r in rows if r.kimp_pct is not None and not r.suspect]
    stats = SnapshotStats(bitkub_count=bitkub_count, bithumb_count=bithumb_count, matched_count=len(matched))
    if matched:
        stats.median_kimp_pct = statistics.median(r.kimp_pct for r in matched)  # type: ignore[misc]
        hi = max(matched, key=lambda r: r.kimp_pct)  # type: ignore[arg-type]
        lo = min(matched, key=lambda r: r.kimp_pct)  # type: ignore[arg-type]
        stats.max_kimp_symbol, stats.max_kimp_pct = hi.symbol, hi.kimp_pct
        stats.min_kimp_symbol, stats.min_kimp_pct = lo.symbol, lo.kimp_pct
    return stats
