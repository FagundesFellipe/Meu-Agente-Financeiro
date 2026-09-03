"""Contrato estável de um canal de mensagens."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from financial_agent.worker.media.shared import MediaPreprocessResult


@runtime_checkable
class ChannelAdapter(Protocol):
    """Tudo que o worker precisa saber sobre um canal, sem saber qual é."""

    name: str

    @classmethod
    def from_settings(cls) -> ChannelAdapter:
        """Constrói o adapter a partir da configuração da aplicação.

        Manter a construção dentro do canal é o que evita que o worker
        conheça os segredos específicos de cada provedor.
        """
        ...

    async def preprocess(
        self, body: str, media_url: str | None, media_type: str | None
    ) -> MediaPreprocessResult:
        """Normaliza a entrada do canal para texto antes de chamar o agente."""
        ...

    async def send_message(self, to: str, body: str) -> object:
        """Envia a resposta final ao usuário pelo canal de origem."""
        ...
