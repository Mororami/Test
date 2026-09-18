"""메모리 내 가격 이력. 단기 급등률 계산에 쓴다."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Mapping


class PriceHistory:
    def __init__(self, max_age_sec: float) -> None:
        self.max_age_sec = max_age_sec
        self._series: dict[str, deque[tuple[float, float]]] = defaultdict(deque)

    def record(self, prices: Mapping[str, float], ts: float) -> None:
        for symbol, price in prices.items():
            if price > 0:
                self._series[symbol].append((ts, price))
        self.prune(ts)

    def prune(self, now: float) -> None:
        cutoff = now - self.max_age_sec
        for symbol in list(self._series):
            series = self._series[symbol]
            while series and series[0][0] < cutoff:
                series.popleft()
            if not series:
                del self._series[symbol]

    def latest(self, symbol: str) -> tuple[float, float] | None:
        series = self._series.get(symbol)
        return series[-1] if series else None

    def price_at(self, symbol: str, target_ts: float, tolerance_sec: float = 0.0) -> float | None:
        """target_ts(+허용 오차) 이전 샘플 중 가장 최근 값. 그만큼 오래된 샘플이 없으면 None."""
        series = self._series.get(symbol)
        if not series:
            return None
        limit = target_ts + tolerance_sec
        found = None
        for ts, price in series:
            if ts > limit:
                break
            found = price
        return found

    def change_pct(self, symbol: str, window_sec: float, now: float,
                   tolerance_sec: float = 0.0) -> float | None:
        """최근 window_sec 동안의 변동률(%). 이력이 부족하면 None."""
        latest = self.latest(symbol)
        if latest is None:
            return None
        past = self.price_at(symbol, now - window_sec, tolerance_sec)
        if past is None or past <= 0:
            return None
        return (latest[1] / past - 1) * 100

    def series(self, symbol: str) -> list[tuple[float, float]]:
        return list(self._series.get(symbol, ()))

    def __len__(self) -> int:
        return len(self._series)
