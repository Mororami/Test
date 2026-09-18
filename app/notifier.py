"""알림 전송: Telegram Bot API (raw HTTP) 와 콘솔."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4000   # Telegram 한도 4096, 여유를 둔다


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class TelegramError(RuntimeError):
    pass


def split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    """빈 줄(알림 경계) 기준으로 나눠 각 조각이 limit 을 넘지 않게 한다."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        while len(block) > limit:            # 한 블록이 너무 길면 강제로 자른다
            if current:
                chunks.append(current)
                current = ""
            chunks.append(block[:limit])
            block = block[limit:]
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx.AsyncClient) -> None:
        self._token = token
        self._chat_id = chat_id
        self._client = client

    async def send(self, text: str) -> None:
        for chunk in split_message(text):
            await self._call("sendMessage", {
                "chat_id": self._chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe", {})

    async def get_updates(self) -> list[dict[str, Any]]:
        return await self._call("getUpdates", {"timeout": 0})

    async def _call(self, method: str, payload: dict[str, Any], _retried: bool = False) -> Any:
        url = TELEGRAM_API.format(token=self._token, method=method)
        response = await self._client.post(url, json=payload)
        data: dict[str, Any] = {}
        try:
            data = response.json()
        except ValueError:
            pass
        if response.status_code == 429 and not _retried:
            wait = float((data.get("parameters") or {}).get("retry_after", 3))
            log.warning("Telegram 429, %.0f초 후 재시도", wait)
            await asyncio.sleep(wait)
            return await self._call(method, payload, _retried=True)
        if not data.get("ok"):
            raise TelegramError(f"{method} 실패 ({response.status_code}): {data.get('description') or response.text[:200]}")
        return data["result"]


class ConsoleNotifier:
    """Telegram 미설정 시 대체. HTML 태그를 벗겨 stdout 에 출력한다."""

    _TAG = re.compile(r"<[^>]+>")

    async def send(self, text: str) -> None:
        print("\n" + self._TAG.sub("", text) + "\n", flush=True)


def build_notifier(cfg, client: httpx.AsyncClient) -> Notifier:
    """Telegram 이 설정돼 있으면 Telegram, 아니면 콘솔 출력."""
    if cfg.telegram.configured:
        return TelegramNotifier(cfg.telegram.bot_token, cfg.telegram.chat_id, client)
    log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없어 알림을 콘솔에만 출력합니다")
    return ConsoleNotifier()
