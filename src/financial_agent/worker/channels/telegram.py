"""Adapter do canal Telegram."""

from __future__ import annotations

from financial_agent.worker.clients.telegram import TelegramClient
from financial_agent.worker.media import telegram as telegram_media
from financial_agent.worker.media.shared import MediaPreprocessResult
from shared.config import settings


class TelegramChannel:
    """Liga o cliente e o pré-processador do Telegram ao contrato do worker."""

    name = "telegram"

    def __init__(self, client: TelegramClient):
        self._client = client

    @classmethod
    def from_settings(cls) -> TelegramChannel:
        bot_token = settings.telegram_bot_token
        return cls(
            TelegramClient(bot_token=bot_token.get_secret_value() if bot_token else "")
        )

    async def preprocess(
        self, body: str, media_url: str | None, media_type: str | None
    ) -> MediaPreprocessResult:
        return await telegram_media.preprocess_incoming_message(
            body, media_url, media_type
        )

    async def send_message(self, to: str, body: str) -> int:
        return await self._client.send_message(to=to, body=body)
