"""수집·계산 결과를 담는 데이터 구조."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Ticker:
    symbol: str                          # 기초자산 심볼 (예: "BTC")
    last: float                          # 마지막 체결가 (호가통화 기준)
    change_24h_pct: float | None = None  # 24h 변동률 (%)
    quote_volume_24h: float | None = None  # 24h 거래대금 (호가통화)
    high_24h: float | None = None
    low_24h: float | None = None
    bid: float | None = None
    ask: float | None = None


@dataclass(slots=True)
class FxRate:
    thb_krw: float          # 1 THB 당 KRW
    source: str             # frankfurter | exchangerate-api | usdt_implied | override
    fetched_at: float       # epoch 초
    as_of: str | None = None  # 제공자 기준 환율 일자


@dataclass(slots=True)
class CoinRow:
    symbol: str
    bitkub_thb: float
    bitkub_krw: float                       # THB 가격 × 환율
    bithumb_krw: float | None = None        # Bithumb 미상장이면 None
    kimp_pct: float | None = None           # (Bithumb / Bitkub환산 - 1) × 100
    change_short_pct: float | None = None   # 최근 N분 Bitkub 변동률
    bitkub_change_24h_pct: float | None = None
    bithumb_change_24h_pct: float | None = None
    bitkub_volume_thb: float | None = None
    bithumb_volume_krw: float | None = None
    suspect: bool = False                   # |김프| 가 비정상적으로 커서 '같은 티커, 다른 코인' 으로 의심

    @property
    def listed_on_bithumb(self) -> bool:
        return self.bithumb_krw is not None


@dataclass(slots=True)
class SnapshotStats:
    bitkub_count: int = 0
    bithumb_count: int = 0
    matched_count: int = 0
    median_kimp_pct: float | None = None
    max_kimp_symbol: str | None = None
    max_kimp_pct: float | None = None
    min_kimp_symbol: str | None = None
    min_kimp_pct: float | None = None


@dataclass(slots=True)
class Snapshot:
    ts: float
    rate_used: FxRate                       # 김프 계산에 실제로 쓴 환율
    forex: FxRate | None                    # 외환 환율 (조회 실패 시 None)
    usdt_implied_thb_krw: float | None      # Bithumb KRW-USDT ÷ Bitkub USDT_THB
    rows: list[CoinRow] = field(default_factory=list)
    stats: SnapshotStats = field(default_factory=SnapshotStats)
    short_window_min: float = 5.0           # change_short_pct 의 기준 시간
    bithumb_stale_sec: float | None = None  # Bithumb 데이터가 캐시된 값이면 그 나이(초)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Alert:
    ts: float
    kind: str        # pump | change_24h | kimp
    symbol: str
    value: float     # 알림 기준이 된 수치 (%)
    text: str        # Telegram 전송용 HTML 본문

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
