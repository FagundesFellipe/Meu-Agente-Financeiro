"""Registro de canais — o único ponto aberto para extensão.

Para suportar um canal novo:

1. crie ``channels/<canal>.py`` implementando ``ChannelAdapter``;
2. acrescente **uma linha** em ``CHANNELS``.

Nenhum outro arquivo do worker precisa ser reaberto.
"""

from __future__ import annotations

from financial_agent.worker.channels.base import ChannelAdapter
from financial_agent.worker.channels.telegram import TelegramChannel
from financial_agent.worker.channels.whatsapp import WhatsAppChannel

CHANNELS: dict[str, type[ChannelAdapter]] = {
    TelegramChannel.name: TelegramChannel,
    WhatsAppChannel.name: WhatsAppChannel,
}


def get_channel(channel: str) -> ChannelAdapter:
    """Resolve o adapter do canal, falhando alto para canais desconhecidos."""
    try:
        adapter = CHANNELS[channel]
    except KeyError:
        raise ValueError(f"Canal não suportado: {channel!r}") from None
    return adapter.from_settings()


__all__ = ["CHANNELS", "ChannelAdapter", "get_channel"]
