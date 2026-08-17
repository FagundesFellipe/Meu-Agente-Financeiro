import structlog
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from financial_agent.server.dependencies import (
    check_rate_limit,
    validate_telegram_secret_token,
)
from src.shared.config import settings
from src.shared.queue import enqueue_or_buffer

logger = structlog.get_logger()


class _TelegramChat(BaseModel):
    id: int
    type: str | None = None


class _TelegramUser(BaseModel):
    id: int
    is_bot: bool | None = None
    first_name: str | None = None
    username: str | None = None


class _TelegramMedia(BaseModel):
    file_id: str
    file_unique_id: str | None = None
    mime_type: str | None = None


class _TelegramPhotoSize(BaseModel):
    file_id: str
    file_unique_id: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None


class _TelegramMessage(BaseModel):
    message_id: int
    from_user: _TelegramUser | None = Field(default=None, alias="from")
    chat: _TelegramChat
    date: int | None = None
    text: str | None = None
    caption: str | None = None
    voice: _TelegramMedia | None = None
    audio: _TelegramMedia | None = None
    video: _TelegramMedia | None = None
    document: _TelegramMedia | None = None
    photo: list[_TelegramPhotoSize] | None = None


class TelegramUpdate(BaseModel):
    """Payload de webhook do Telegram."""

    update_id: int
    message: _TelegramMessage | None = None
    edited_message: _TelegramMessage | None = None
    channel_post: _TelegramMessage | None = None
    edited_channel_post: _TelegramMessage | None = None


router = APIRouter(tags=["webhook", "telegram"])


@router.post("/webhook/telegram")
async def webhook_telegram(
    update: TelegramUpdate,
    agent: str = Query(
        description="ID do agente para processar a mensagem",
    ),
    _token: None = Depends(validate_telegram_secret_token),
) -> Response:
    """Recebe updates do Telegram e enfileira para processamento pelo worker.

    Extrai o chat_id como identificador do usuário e delega todo o
    processamento (inclusive resolução de file_id -> URL) ao worker.
    """
    message = (
        update.message
        or update.edited_message
        or update.channel_post
        or update.edited_channel_post
    )
    if message is None:
        logger.debug(
            "telegram_webhook_no_message",
            update_id=update.update_id,
        )
        return Response(status_code=200)

    chat_id = str(message.chat.id)
    external_message_id = str(message.message_id)
    body = (message.text or message.caption or "").strip()

    media_url: str | None = None
    media_type: str | None = None

    if message.voice:
        media_url = message.voice.file_id
        media_type = message.voice.mime_type or "audio/ogg"
    elif message.audio:
        media_url = message.audio.file_id
        media_type = message.audio.mime_type or "audio/mpeg"
    elif message.video:
        media_url = message.video.file_id
        media_type = message.video.mime_type or "video/mp4"
    elif message.document:
        media_url = message.document.file_id
        media_type = message.document.mime_type or "application/octet-stream"
    elif message.photo:
        # Telegram envia vários tamanhos; usamos a maior resolução.
        largest = max(message.photo, key=lambda p: (p.width or 0) * (p.height or 0))
        media_url = largest.file_id
        media_type = "image/jpeg"

    if not body and not media_url:
        logger.debug(
            "telegram_webhook_empty_message",
            chat_id=chat_id,
            update_id=update.update_id,
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
