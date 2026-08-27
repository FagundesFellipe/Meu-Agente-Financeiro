from collections.abc import Mapping

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from financial_agent.server.dependencies import (
    validate_telegram_secret_token,
    validate_twilio_signature,
)
from shared.config import settings


def _request(headers: Mapping[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/webhook/test",
            "query_string": b"",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in (headers or {}).items()
            ],
            "server": ("testserver", 443),
        }
    )


async def test_twilio_webhook_fails_closed_without_auth_token(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")

    with pytest.raises(HTTPException) as exc_info:
        await validate_twilio_signature(_request())

    assert exc_info.value.status_code == 503


async def test_telegram_webhook_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret_token", None)

    with pytest.raises(HTTPException) as exc_info:
        await validate_telegram_secret_token(_request())

    assert exc_info.value.status_code == 503


async def test_telegram_webhook_rejects_missing_secret_header(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret_token", "test-secret")

    with pytest.raises(HTTPException) as exc_info:
        await validate_telegram_secret_token(_request())

    assert exc_info.value.status_code == 403
