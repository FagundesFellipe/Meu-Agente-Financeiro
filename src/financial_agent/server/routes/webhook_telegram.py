"""Webhook Telegram - Processamento assíncrono via fila.

Recebe updates do Telegram, valida, aplica rate limit e adiciona na fila
para processamento via worker.

Fluxo:
Telegram -> POST /webhook/telegram -> Fila (Postgres) -> Worker
"""

import structlog
from fastapi import APIRouter, Body, Depends, Query, Response

from financial_agent.server.dependencies import (
    check_rate_limit,
    validate_telegram_secret_token,
)
from src.shared.config import settings
from src.shared.queue import enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(tags=["webhook", "telegram"])

_MESSAGE_EXAMPLE = {
    "message_id": 1,
    "from": {
        "id": 111111,
        "is_bot": False,
        "first_name": "Fellipe",
        "username": "fellipe",
    },
    "chat": {"id": 111111, "type": "private"},
    "date": 1700000000,
    "text": "Gastei 35 reais no almoço",
}


@router.post("/webhook/telegram")
async def webhook_telegram(
    agent: str = Query(
        description="ID do agente para processar a mensagem.",
    ),
    update_id: int = Body(
        description="ID sequencial do update no Telegram.",
    ),
    message: dict | None = Body(
        default=None,
        description="Nova mensagem recebida.",
        examples=[_MESSAGE_EXAMPLE],
    ),
    edited_message: dict | None = Body(
        default=None,
        description="Mensagem editada.",
    ),
    channel_post: dict | None = Body(
        default=None,
        description="Novo post em canal.",
    ),
    edited_channel_post: dict | None = Body(
        default=None,
        description="Post de canal editado.",
    ),
    _token: None = Depends(validate_telegram_secret_token),
) -> Response:
    """Recebe updates do Telegram e enfileira para processamento pelo worker.

    Extrai o chat_id como identificador do usuário e delega todo o
    processamento (inclusive resolução de file_id -> URL) ao worker.
    """
    msg = message or edited_message or channel_post or edited_channel_post
    if msg is None:
        logger.debug("telegram_webhook_no_message", update_id=update_id)
        return Response(status_code=200)

    chat_id = str(msg["chat"]["id"])
    external_message_id = str(msg["message_id"])
    body = (msg.get("text") or msg.get("caption") or "").strip()

    media_url: str | None = None
    media_type: str | None = None

    if voice := msg.get("voice"):
        media_url = voice["file_id"]
        media_type = voice.get("mime_type") or "audio/ogg"
    elif audio := msg.get("audio"):
        media_url = audio["file_id"]
        media_type = audio.get("mime_type") or "audio/mpeg"
    elif video := msg.get("video"):
        media_url = video["file_id"]
        media_type = video.get("mime_type") or "video/mp4"
    elif document := msg.get("document"):
        media_url = document["file_id"]
        media_type = document.get("mime_type") or "application/octet-stream"
    elif photo := msg.get("photo"):
        # Telegram envia vários tamanhos; usamos a maior resolução.
        largest = max(
            photo, key=lambda p: (p.get("width") or 0) * (p.get("height") or 0)
        )
        media_url = largest["file_id"]
        media_type = "image/jpeg"

    if not body and not media_url:
        logger.debug(
            "telegram_webhook_empty_message",
            chat_id=chat_id,
            update_id=update_id,
            message_id=external_message_id,
        )
        return Response(status_code=200)

    await check_rate_limit(chat_id)

    result = await enqueue_or_buffer(
        channel="telegram",
        phone_number=chat_id,
        agent_id=agent,
        body=body,
        media_url=media_url,
        media_type=media_type,
        message_id=external_message_id,
        buffer_seconds=settings.message_buffer_seconds,
    )

    logger.info(
        "webhook_telegram_received",
        chat_id=chat_id,
        agent_id=agent,
        message_id=result.message_id,
        buffered=result.is_buffered,
    )

    return Response(status_code=200)
