"""Pré-processamento de mídia recebida pelo Telegram Bot API."""

from __future__ import annotations

import httpx

from financial_agent.worker.media.shared import (
    MediaPreprocessResult,
)
from financial_agent.worker.media.shared import (
    preprocess_incoming_message as _preprocess_incoming_message,
)
from shared.config import settings

TELEGRAM_API_BASE_URL = "https://api.telegram.org"


def _bot_token() -> str:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")
    return token.get_secret_value()


async def download_media(file_id: str) -> bytes:
    """Resolve um ``file_id`` e baixa seu conteúdo pelo Bot API.

    O Telegram exige primeiro ``getFile``; a resposta contém ``file_path``, que
    compõe a URL oficial de download. O token nunca é derivado do payload.
    """
    token = _bot_token()
    async with httpx.AsyncClient(timeout=45.0) as client:
        metadata_response = await client.get(
            f"{TELEGRAM_API_BASE_URL}/bot{token}/getFile",
            params={"file_id": file_id},
        )
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        if not metadata.get("ok"):
            raise RuntimeError("Telegram getFile não retornou sucesso")
        file_path = metadata.get("result", {}).get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise RuntimeError("Telegram getFile não retornou file_path")

        download_response = await client.get(
            f"{TELEGRAM_API_BASE_URL}/file/bot{token}/{file_path}"
        )
        download_response.raise_for_status()
        return download_response.content


async def preprocess_incoming_message(
    body: str, media_url: str | None = None, media_type: str | None = None
) -> MediaPreprocessResult:
    """Resolve a mídia Telegram (cuja URL é o ``file_id``) e a transcreve."""
    return await _preprocess_incoming_message(
        body, media_url, media_type, download_media
    )
