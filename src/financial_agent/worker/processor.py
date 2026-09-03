"""Processador de mensagens — orquestra agente e fila.

Responsável por:
1. Construir a HumanMessage (com mídia se houver)
2. Carregar o agente via loader (com checkpointer PostgreSQL)
3. Executar o agente
4. Salvar a resposta no banco (mark_done ou mark_failed)

Uso:
    from financial_agent.worker.processor import process_message

    await process_message(message, checkpointer=ckeckpointer)
"""

from typing import cast

import structlog
from langchain_core.messages import HumanMessage

from financial_agent.agent.build_graph_workflow import graph
from financial_agent.worker.channels import get_channel
from financial_agent.worker.media.shared import AUTO_RESPONSE_MEDIA_FAILURE
from shared.queue import (
    Channel,
    hold_thread_processing_lock,
    mark_done,
    mark_failed,
    upsert_conversation,
)
from shared.repositories.queue import MessageQueue

logger = structlog.get_logger()


async def _process_claimed_message(message: MessageQueue) -> None:
    """Executa uma mensagem enquanto a posse da conversa está protegida."""
    claim_token = message.claim_token
    if claim_token is None:
        raise RuntimeError("claimed_message_without_claim_token")

    channel = get_channel(message.channel)
    preprocessed = await channel.preprocess(
        message.incoming_message, message.media_url, message.media_type
    )

    if not preprocessed.should_invoke_agent:
        response_text = preprocessed.auto_response or AUTO_RESPONSE_MEDIA_FAILURE
    else:
        compiled_graph = await graph()
        result = await compiled_graph.ainvoke(
            {
                "messages": [HumanMessage(content=preprocessed.normalized_text or "")],
                "phone_number": message.phone_number,
                "channel": message.channel,
                "message_id": message.id,
            },
            config={
                "configurable": {"thread_id": message.thread_id},
                "metadata": {"thread_id": str(message.thread_id)},
            },
        )
        response_text = result["messages"][-1].content

    completed = await mark_done(
        message.id,
        claim_token,
        response_text,
        normalized_input=preprocessed.normalized_text,
        media_processing_status=preprocessed.media_processing_status,
        media_processing_error=preprocessed.media_processing_error,
    )
    if not completed:
        return

    await channel.send_message(to=message.phone_number, body=response_text)

    await upsert_conversation(
        phone_number=message.phone_number,
        channel=cast(Channel, message.channel),
        agent_id=message.agent_id,
        last_message=response_text,
    )


async def process_message(message: MessageQueue) -> None:
    """Processa uma mensagem da fila: pré-processa, executa o agente e responde.

    Args:
        message: Mensagem reivindicada da fila (``message_queue``).
    """
    try:
        async with hold_thread_processing_lock(message.thread_id):
            await _process_claimed_message(message)
    except Exception as exc:
        logger.error(
            "message_processing_failed",
            message_id=message.id,
            error_type=type(exc).__name__,
        )
        if message.claim_token is not None:
            await mark_failed(message.id, message.claim_token, str(exc))
