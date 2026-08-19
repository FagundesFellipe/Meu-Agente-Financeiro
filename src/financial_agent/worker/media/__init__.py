"""Pré-processadores de mídia por canal."""

from typing import Literal

from financial_agent.worker.media.shared import MediaPreprocessResult


async def preprocess_incoming_message(
    channel: Literal["telegram", "whatsapp"],
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
) -> MediaPreprocessResult:
    """Escolhe o pré-processador adequado ao canal de origem."""
    if channel == "telegram":
        from financial_agent.worker.media.telegram import (
            preprocess_incoming_message as preprocess_telegram,
        )

        return await preprocess_telegram(body, media_url, media_type)

    if channel == "whatsapp":
        from financial_agent.worker.media.whatsapp import (
            preprocess_incoming_message as preprocess_whatsapp,
        )

        return await preprocess_whatsapp(body, media_url, media_type)

    raise ValueError(f"Canal de mídia não suportado: {channel!r}")


__all__ = ["MediaPreprocessResult", "preprocess_incoming_message"]
