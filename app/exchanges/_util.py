from __future__ import annotations

from typing import Any


def num(value: Any) -> float | None:
    """API 가 문자열/숫자/None 을 섞어 주므로 안전하게 float 로 바꾼다."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
