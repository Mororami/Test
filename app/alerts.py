"""알림 조건 판정 (급등 / 24h 변동 / 김프) 과 메시지 생성."""
from __future__ import annotations

import html
import time
from typing import Iterator

from app.config import AlertConfig
from app.fmt import fmt_compact, fmt_krw, fmt_pct, fmt_thb
from app.models import Alert, CoinRow, Snapshot

KIND_PUMP = "pump"
KIND_CHANGE_24H = "change_24h"
KIND_KIMP = "kimp"
KIND_LABELS = {KIND_PUMP: "급등", KIND_CHANGE_24H: "24h 급등", KIND_KIMP: "김프"}


def _volume_ok(value: float | None, minimum: float) -> bool:
    return minimum <= 0 or (value is not None and value >= minimum)


class AlertEngine:
    """조건이 '처음' 충족될 때만 알리고(엣지 트리거), 같은 코인·종류는 cooldown 동안 재발송하지 않는다."""

    def __init__(self, cfg: AlertConfig) -> None:
        self.cfg = cfg
        self._last_sent: dict[tuple[str, str], float] = {}
        self._active: set[tuple[str, str]] = set()

    def evaluate(self, snapshot: Snapshot, now: float | None = None) -> list[Alert]:
        now = time.time() if now is None else now
        cooldown = self.cfg.cooldown_min * 60
        alerts: list[Alert] = []
        for row in snapshot.rows:
            for kind, triggered, value in self._conditions(row):
                key = (kind, row.symbol)
                if not triggered:
                    self._active.discard(key)   # 조건이 풀리면 다음 충족 때 다시 알릴 수 있게 재무장
                    continue
                if key in self._active:
                    continue
                self._active.add(key)
                last = self._last_sent.get(key)
                if last is not None and now - last < cooldown:
                    continue
                self._last_sent[key] = now
                alerts.append(Alert(ts=now, kind=kind, symbol=row.symbol, value=value,
                                    text=format_alert(kind, row, snapshot)))
        return alerts

    def _conditions(self, row: CoinRow) -> Iterator[tuple[str, bool, float]]:
        pump = self.cfg.pump
        if pump.enabled:
            v = row.change_short_pct
            hit = v is not None and v >= pump.threshold_pct and _volume_ok(row.bitkub_volume_thb, pump.min_quote_volume_thb)
            yield KIND_PUMP, hit, (v or 0.0)
        c24 = self.cfg.change_24h
        if c24.enabled:
            v = row.bitkub_change_24h_pct
            hit = v is not None and v >= c24.threshold_pct and _volume_ok(row.bitkub_volume_thb, c24.min_quote_volume_thb)
            yield KIND_CHANGE_24H, hit, (v or 0.0)
        kimp = self.cfg.kimp
        if kimp.enabled:
            v = row.kimp_pct
            hit = (v is not None and not row.suspect and abs(v) >= kimp.threshold_pct
                   and _volume_ok(row.bitkub_volume_thb, kimp.min_quote_volume_thb)
                   and _volume_ok(row.bithumb_volume_krw, kimp.min_quote_volume_krw))
            yield KIND_KIMP, hit, (v or 0.0)


def format_alert(kind: str, row: CoinRow, snapshot: Snapshot) -> str:
    sym = html.escape(row.symbol)
    window = _minutes(snapshot.short_window_min)
    price_line = f"Bitkub: {fmt_thb(row.bitkub_thb)} ≈ {fmt_krw(row.bitkub_krw)}"
    if kind == KIND_PUMP:
        head = f"🚀 <b>{sym} 급등</b> (Bitkub {window} {fmt_pct(row.change_short_pct)})"
    elif kind == KIND_CHANGE_24H:
        head = f"📈 <b>{sym} 24h 급등</b> (Bitkub {fmt_pct(row.bitkub_change_24h_pct)})"
    else:
        arrow = "🔺" if (row.kimp_pct or 0) >= 0 else "🔻"
        head = f"{arrow} <b>{sym} 김프 {fmt_pct(row.kimp_pct)}</b>"

    lines = [head, price_line,
             f"24h {fmt_pct(row.bitkub_change_24h_pct)} | {window} {fmt_pct(row.change_short_pct)}"
             f" | 거래대금 {fmt_compact(row.bitkub_volume_thb)} THB"]
    if row.listed_on_bithumb:
        lines.append(f"Bithumb: {fmt_krw(row.bithumb_krw)} | 24h {fmt_pct(row.bithumb_change_24h_pct)}"
                     f" | 김프 {fmt_pct(row.kimp_pct)}")
    else:
        lines.append("Bithumb: 미상장")
    lines.append(f"<i>환율 1 THB = {snapshot.rate_used.thb_krw:.3f}원 ({snapshot.rate_used.source})</i>")
    return "\n".join(lines)


def format_startup(snapshot_interval_sec: float, cfg: AlertConfig) -> str:
    parts = ["🤖 <b>Bitkub 시세 알람 봇 시작</b>", f"수집 주기: {snapshot_interval_sec:g}초"]
    if cfg.pump.enabled:
        parts.append(f"급등: {_minutes(cfg.pump.window_min)} 내 +{cfg.pump.threshold_pct:g}% 이상")
    if cfg.change_24h.enabled:
        parts.append(f"24h 변동: +{cfg.change_24h.threshold_pct:g}% 이상")
    if cfg.kimp.enabled:
        parts.append(f"김프: |{cfg.kimp.threshold_pct:g}%| 이상")
    parts.append(f"재알림 간격: {cfg.cooldown_min:g}분")
    return "\n".join(parts)


def _minutes(value: float) -> str:
    return f"{value:g}분"
