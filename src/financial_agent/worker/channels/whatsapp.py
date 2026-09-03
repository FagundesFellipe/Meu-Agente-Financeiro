"""Adapter do canal WhatsApp (via Twilio)."""

from __future__ import annotations

from financial_agent.worker.clients.twilio import TwilioClient
from financial_agent.worker.media import whatsapp as whatsapp_media
from financial_agent.worker.media.shared import MediaPreprocessResult
from shared.config import settings


class WhatsAppChannel:
    """Liga o cliente Twilio e o pré-processador WhatsApp ao contrato."""

    name = "whatsapp"

    def __init__(self, client: TwilioClient):
        self._client = client

    @classmethod
    def from_settings(cls) -> WhatsAppChannel:
        return cls(
            TwilioClient(
                account_sid=settings.twilio_account_sid,
                api_key_sid=settings.twilio_api_key_sid,
                api_key_secret=settings.twilio_api_key_secret,
                from_number=settings.twilio_from_number,
                delivery_mode=settings.resolved_twilio_outbound_mode,
            )
        )

    async def preprocess(
        self, body: str, media_url: str | None, media_type: str | None
    ) -> MediaPreprocessResult:
        return await whatsapp_media.preprocess_incoming_message(
            body, media_url, media_type
        )

    async def send_message(self, to: str, body: str) -> str:
        return await self._client.send_message(to=to, body=body)
