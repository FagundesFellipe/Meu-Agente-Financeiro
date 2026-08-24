"""Webhook - Processamento assíncrono via fila.

Recebe mensagens via Twilio ou Telegram, valida, aplica rate limit e adiciona na fila
para processamento via worker.

Fluxo:
Twilio ->   POST    /webhook/twilio ->
                                        Fila (Postgres) -> Worker
Telegram -> POST /webhook/telegram ->

"""

from typing import NamedTuple

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response

from financial_agent.server.dependencies import (
    check_rate_limit,
    validate_twilio_signature,
)
from shared.config import settings
from shared.queue import enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(tags=["webhook"])


class TwilioMedia(NamedTuple):
    url: str | None
    type: str | None


@router.post("/webhook/twilio")
async def webhook_twilio(
    agent: str = Query(
        description="ID do agente para processar a mensagem",
    ),
    message_sid: str = Form(
        default="",
        alias="MessageSid",
        description="ID da mensagem no Twilio (MessageSid).",
    ),
    from_number: str = Form(
        default="",
        alias="From",
        description="Número remetente no formato whatsapp:+55...",
    ),
    to_number_form: str = Form(
        default="",
        alias="To",
        description="Número de destino no formato whatsapp:+...",
    ),
    body: str = Form(
        default="",
        alias="Body",
        description="Texto da mensagem (pode ser vazio em mensagens de mídia).",
    ),
    num_media_raw: str = Form(
        default="0",
        alias="NumMedia",
        description="Quantidade de mídias anexadas.",
    ),
    media_url_form: str | None = Form(
        default=None,
        alias="MediaUrl0",
        description="URL da primeira mídia (quando NumMedia > 0).",
    ),
    media_type_form: str | None = Form(
        default=None,
        alias="MediaContentType0",
        description="MIME type da primeira mídia.",
    ),
    wa_id: str = Form(
        default="",
        alias="WaId",
        description="WhatsApp Id do remetente (Fallback de From)",
    ),
    _signature: None = Depends(validate_twilio_signature),
) -> Response:
    phone_number = resolve_sender_phone(from_number=from_number, wa_id=wa_id)
    to_number = strip_whatsapp_prefix(to_number_form)

    body = body or ""
    message_sid = message_sid or ""

    if not phone_number:
        logger.warning(
            "Webhook_missing_sender",
            message_sid=message_sid,
            from_raw=from_number,
            wa_id_raw=wa_id,
        )
        raise HTTPException(
            status_code=400, detail="Missing sender identify (From/Wa_ID)"
        )

    try:
        num_media = int(num_media_raw or "0")
    except ValueError:
        num_media = 0

    media = extract_twilio_media(
        num_media, url_form=media_url_form, type_form=media_type_form
    )

    await check_rate_limit(phone_number)

    result = await enqueue_or_buffer(
        channel="whatsapp",
        phone_number=phone_number,
        agent_id=agent,
        body=body,
        media_url=media.url,
        media_type=media.type,
        to_number=to_number,
        message_id=message_sid,
        buffer_seconds=settings.message_buffer_seconds,
    )

    EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

    logger.info(
        "webhook_twilio_received",
        phone=phone_number,
        agent_id=agent,
        message_id=result.message_id,
        buffered=result.is_buffered,
    )

    return Response(content=EMPTY_TWIML, media_type="application/xml")


def strip_whatsapp_prefix(value: str) -> str:
    return (value or "").replace("whatsapp:", "")


def resolve_sender_phone(from_number: str, wa_id: str) -> str:
    phone = strip_whatsapp_prefix(from_number)
    if not phone and wa_id:
        phone = wa_id if wa_id.startswith("+") else f"+{wa_id}"
    return phone


def extract_twilio_media(
    num_media: int, url_form: str | None, type_form: str | None
) -> TwilioMedia:
    if num_media <= 0:
        return TwilioMedia(None, None)
    return TwilioMedia(
        url_form.strip() if url_form else None,
        type_form.strip() if type_form else None,
    )
