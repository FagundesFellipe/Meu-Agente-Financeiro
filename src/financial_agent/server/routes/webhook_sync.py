"""Webhook síncrono — endpoints educacionais para testes rápidos.

Processa mensagens WhatsApp e Telegram inline e retorna a resposta diretamente.
Útil para testes rápidos sem worker rodando, demonstrações e debugging.

NÃO USAR EM PRODUÇÃO — sem debounce, fila, retry ou rate limit.

Uso:
    # WhatsApp
    curl -X POST "http://localhost:8000/webhook/sync/whatsapp" \
         -H "Content-Type: application/json" \
         -d '{"phone": "+5511999999999", "message": "Gastei 35 no almoço"}'

    # Telegram
    curl -X POST "http://localhost:8000/webhook/sync/telegram" \
         -H "Content-Type: application/json" \
         -d '{"chat_id": "987654321", "message": "Gastei 35 no almoço"}'
"""

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from financial_agent.agent.build_graph_workflow import graph as load_graph
from src.shared.config import settings

logger = structlog.get_logger()
router = APIRouter(tags=["webhook"])


class SyncRequestWhatsapp(BaseModel):
    """Payload do webhook síncrono."""

    phone: str = Field(description="Número do remetente (E.164)")
    message: str = Field(description="Texto da mensagem")


class SyncRequestTelegram(BaseModel):
    """Payload do webhook síncrono para Telegram."""

    chat_id: str = Field(description="ID do chat no Telegram (número como string)")
    message: str = Field(description="Texto da mensagem")


class SyncResponse(BaseModel):
    """Resposta do webhook síncrono."""

    response: str = Field(description="Resposta após processamento do grafo")
    agent_id: str


@router.post("/webhook/sync/whatsapp", response_model=SyncResponse)
async def webhook_whatsapp_sync(payload: SyncRequestWhatsapp) -> SyncResponse:
    """Processa mensagem de forma síncrona (sem fila)"""

    logger.info(
        "webhook_whatsapp_sync_received",
        phone=payload.phone,
        agent_id=settings.agent_id,
    )

    graph = await load_graph()

    thread_id = f"{payload.phone}:{settings.agent_id}"
    result = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": payload.message}],
            "phone_number": payload.phone,
            "channel": "whatsapp",
        },
        config={"configurable": {"thread_id": thread_id, "user_id": payload.phone}},
    )

    response_text = result["messages"][-1].content

    logger.info(
        "webhook_whatsapp_sync_responded",
        phone=payload.phone,
        agent_id=settings.agent_id,
    )

    return SyncResponse(response=response_text, agent_id=settings.agent_id)


@router.post("/webhook/sync/telegram", response_model=SyncResponse)
async def webhook_telegram_sync(payload: SyncRequestTelegram) -> SyncResponse:
    """Processa mensagem do Telegram de forma síncrona (sem fila).

    O Telegram identifica usuários por chat_id (inteiro), não por telefone.
    Aqui recebemos como string para compatibilidade com o modelo interno,
    que já suporta ``channel="telegram"`` e ``external_user_id`` genérico.
    """

    logger.info(
        "webhook_telegram_sync_received",
        chat_id=payload.chat_id,
        agent_id=settings.agent_id,
    )

    graph = await load_graph()

    thread_id = f"{payload.chat_id}:{settings.agent_id}"
    result = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": payload.message}],
            "phone_number": payload.chat_id,
            "channel": "telegram",
        },
        config={"configurable": {"thread_id": thread_id, "user_id": payload.chat_id}},
    )

    response_text = result["messages"][-1].content

    logger.info(
        "webhook_telegram_sync_responded",
        chat_id=payload.chat_id,
        agent_id=settings.agent_id,
    )

    return SyncResponse(response=response_text, agent_id=settings.agent_id)
