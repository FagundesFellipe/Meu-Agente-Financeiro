"""Pré-processamento de mídia recebida pelo WhatsApp via Twilio."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from financial_agent.worker.media.shared import (
    MediaPreprocessResult,
)
from financial_agent.worker.media.shared import (
    preprocess_incoming_message as _preprocess_incoming_message,
)
from shared.config import settings

ALLOWED_MEDIA_HOSTS = {"api.twilio.com"}


async def download_media(url: str) -> bytes:
    """Baixa mídia da Twilio, somente de hosts autorizados."""
    host = urlparse(url).hostname
    if host not in ALLOWED_MEDIA_HOSTS:
        raise ValueError(f"Host de mídia não permitido: {host!r}")

    auth = (
        (settings.twilio_api_key_sid, settings.twilio_api_key_secret)
        if settings.twilio_api_key_sid
        else None
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(url, auth=auth, follow_redirects=True)
        response.raise_for_status()
        return response.content


async def preprocess_incoming_message(
    body: str, media_url: str | None = None, media_type: str | None = None
) -> MediaPreprocessResult:
    return await _preprocess_incoming_message(
        body, media_url, media_type, download_media
    )
