"""숫자 표시 포맷 (봇 메시지·콘솔 공용)."""
from __future__ import annotations

import math


def fmt_num(value: float | None) -> str:
    """가격 크기에 맞춰 소수 자릿수를 조절한다."""
    if value is None:
        return "-"
    v = abs(value)
    if v >= 1000:
        return f"{value:,.0f}"
    if v >= 1:
        return f"{value:,.2f}"
    if v >= 0.01:
        return f"{value:.4f}"
    digits = min(12, 3 - int(math.floor(math.log10(v))))   # 유효숫자 4자리, 지수 표기 없이
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def fmt_thb(value: float | None) -> str:
    return "-" if value is None else f"{fmt_num(value)} THB"


def fmt_krw(value: float | None) -> str:
    return "-" if value is None else f"{fmt_num(value)}원"


def fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:+.{digits}f}%"


def fmt_compact(value: float | None) -> str:
    """거래대금처럼 큰 수를 1.2K / 3.4M / 5.6B 로 줄인다."""
    if value is None:
        return "-"
    v = abs(value)
    sign = "-" if value < 0 else ""
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= size:
            return f"{sign}{v / size:.1f}{unit}"
    return f"{sign}{v:,.0f}"
