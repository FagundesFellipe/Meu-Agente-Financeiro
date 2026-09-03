"""Pré-processadores de mídia por canal.

A seleção do canal vive em ``financial_agent.worker.channels``; este módulo
expõe apenas o resultado compartilhado do pré-processamento.
"""

from financial_agent.worker.media.shared import MediaPreprocessResult

__all__ = ["MediaPreprocessResult"]
