import json

import httpx
import pytest

from financial_agent.worker.clients.telegram import TelegramClient, TelegramSendError


async def test_send_message_posts_json_and_returns_message_id(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 123}})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    client = TelegramClient("test-token")

    assert await client.send_message(456, "Olá") == 123
    assert requests[0].url == "https://api.telegram.org/bottest-token/sendMessage"
    assert requests[0].method == "POST"
    assert json.loads(requests[0].content) == {"chat_id": 456, "text": "Olá"}


@pytest.mark.parametrize("body", ["", "a" * 4097])
async def test_send_message_rejects_invalid_body(body: str) -> None:
    client = TelegramClient("test-token")

    with pytest.raises(ValueError):
        await client.send_message(456, body)


async def test_send_message_raises_for_telegram_failure(monkeypatch) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"ok": False, "error_code": 400, "description": "chat not found"},
        )

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    client = TelegramClient("test-token")

    with pytest.raises(TelegramSendError, match="400.*chat not found"):
        await client.send_message(456, "Olá")


async def test_send_message_rejects_non_object_json_response(monkeypatch) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    client = TelegramClient("test-token")

    with pytest.raises(TelegramSendError, match="resposta inválida"):
        await client.send_message(456, "Olá")


async def test_send_typing_uses_send_chat_action(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    client = TelegramClient("test-token")

    assert await client.send_typing("456") is True
    assert requests[0].url == "https://api.telegram.org/bottest-token/sendChatAction"
    assert json.loads(requests[0].content) == {"chat_id": "456", "action": "typing"}


async def test_send_typing_returns_false_for_non_object_json_response(
    monkeypatch,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    client = TelegramClient("test-token")

    assert await client.send_typing(456) is False


async def test_mock_mode_does_not_call_telegram() -> None:
    client = TelegramClient("", delivery_mode="mock")

    assert await client.send_message(456, "Olá") == 0
    assert await client.send_typing(456) is False
