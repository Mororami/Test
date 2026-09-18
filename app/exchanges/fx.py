"""THB→KRW 환율. 1차 frankfurter(ECB), 2차 exchangerate-api. 실패 시 이전 값 유지."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

import httpx

from app.models import FxRate

log = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
ER_API_URL = "https://open.er-api.com/v6/latest/THB"


class FxUnavailable(RuntimeError):
    """어떤 소스에서도 환율을 얻지 못했고 캐시도 없다."""


class FxClient:
    def __init__(self, client: httpx.AsyncClient, refresh_sec: float = 3600,
                 override: float | None = None) -> None:
        self._client = client
        self._refresh_sec = refresh_sec
        self._override = override
        self._cached: FxRate | None = None
        self._sources: list[tuple[str, Callable[[], Awaitable[tuple[float, str | None]]]]] = [
            ("frankfurter", self._frankfurter),
            ("exchangerate-api", self._er_api),
        ]

    @property
    def cached(self) -> FxRate | None:
        return self._cached

    async def get_thb_krw(self, now: float | None = None) -> FxRate:
        now = time.time() if now is None else now
        if self._override is not None:
            return FxRate(thb_krw=self._override, source="override", fetched_at=now)
        if self._cached is not None and now - self._cached.fetched_at < self._refresh_sec:
            return self._cached

        errors = []
        for name, fetch in self._sources:
            try:
                rate, as_of = await fetch()
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{name}: {exc}")
                continue
            self._cached = FxRate(thb_krw=rate, source=name, fetched_at=now, as_of=as_of)
            log.info("환율 갱신: 1 THB = %.4f KRW (%s, %s)", rate, name, as_of)
            return self._cached

        if self._cached is not None:
            log.warning("환율 갱신 실패, 이전 값(%.4f, %s) 유지: %s",
                        self._cached.thb_krw, self._cached.source, "; ".join(errors))
            return self._cached
        raise FxUnavailable("; ".join(errors))

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def _frankfurter(self) -> tuple[float, str | None]:
        data = await self._get_json(FRANKFURTER_URL, {"base": "THB", "symbols": "KRW"})
        return _positive(data["rates"]["KRW"]), data.get("date")

    async def _er_api(self) -> tuple[float, str | None]:
        data = await self._get_json(ER_API_URL)
        if data.get("result") != "success":
            raise ValueError(f"result={data.get('result')}")
        return _positive(data["rates"]["KRW"]), data.get("time_last_update_utc")


def _positive(value: Any) -> float:
    rate = float(value)
    if rate <= 0:
        raise ValueError(f"환율이 0 이하입니다: {rate}")
    return rate
