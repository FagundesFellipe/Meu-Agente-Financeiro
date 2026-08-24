"""Consumidor de mensagens da fila

Uso:
    from financial_agent.worker.consumer import claim_next_message

    message = await claim_next_message(lease_seconds=60)
    if message:
        await process_message(message)
"""

import structlog

from shared.queue import claim_next

logger = structlog.get_logger()


async def claim_next_message(lease_seconds: int = 60):
    """Busca a próxima mensagem pronta da fila

    Args:
        pool: Pool de conexões do psycopg.
        lease_seconds: Segundos de lock para processamento.

    Returns:
        MessageQueue se houver mensagem, None se a fila está vazia.
    """

    message = await claim_next(lease_seconds)

    if message is None:
        logger.info("queue_empty")

    return message
