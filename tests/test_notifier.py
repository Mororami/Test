import asyncio
import json

import httpx
import pytest

from app.notifier import MAX_MESSAGE_LEN, ConsoleNotifier, TelegramError, TelegramNotifier, split_message
from tests.conftest import json_response, mock_client


def test_split_message_on_blank_lines():
    blocks = [f"alert {i}\n" + "x" * 1500 for i in range(5)]
    chunks = split_message("\n\n".join(blocks), limit=4000)
    assert len(chunks) == 3
    assert all(len(c) <= 4000 for c in chunks)
    assert "\n\n".join(chunks) == "\n\n".join(blocks)      # 내용 손실 없음
    assert split_message("short") == ["short"]
    long_block = "y" * (MAX_MESSAGE_LEN + 10)
    assert [len(c) for c in split_message(long_block)] == [MAX_MESSAGE_LEN, 10]


async def test_telegram_send_and_error():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        seen.append((request.url.path, body))
        if "boom" in body:
            return json_response({"ok": False, "description": "Bad Request: chat not found"}, status=400)
        return json_response({"ok": True, "result": {"message_id": 1}})

    async with mock_client(handler) as client:
        tg = TelegramNotifier("TOKEN", "123", client)
        await tg.send("<b>hi</b>")
        with pytest.raises(TelegramError, match="chat not found"):
            await tg.send("boom")
    assert seen[0][0] == "/botTOKEN/sendMessage"
    payload = json.loads(seen[0][1])
    assert payload["parse_mode"] == "HTML" and payload["chat_id"] == "123" and payload["text"] == "<b>hi</b>"


async def test_telegram_429_retries_once(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return json_response({"ok": False, "parameters": {"retry_after": 2}}, status=429)
        return json_response({"ok": True, "result": True})

    async with mock_client(handler) as client:
        await TelegramNotifier("T", "1", client).send("x")
    assert calls["n"] == 2 and sleeps == [2.0]


async def test_console_notifier_strips_tags(capsys):
    await ConsoleNotifier().send("<b>급등</b> BTC")
    assert "급등 BTC" in capsys.readouterr().out
