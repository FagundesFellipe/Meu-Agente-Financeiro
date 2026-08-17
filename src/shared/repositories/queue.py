from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class EnqueueResult(BaseModel):
    """Resultado de uma operação de enqueue.

    Indica se a mensagem foi inserida na fila ou buffered (debounce).
    """

    message_id: UUID
    is_buffered: bool = Field(
        default=False,
        description="True se a mensagem foi concatenada a uma existente (debounce)",
    )


class MessageStatus(str, Enum):
    """Status possíveis de uma mensagem na fila.

    Fluxo: queued → processing → done | failed
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class MessageQueue(BaseModel):
    """Mapeamento da tabela message_queue.

    Representa uma mensagem na fila de processamento.
    O Worker consome mensagens com status 'queued' e as processa.
    """

    id: int
    message_id: str | None = None
    phone_number: str = Field(description="Formato E.164, ex: +5511999999999")
    to_number: str | None = None
    agent_id: str = Field(description="Identificador do agente em langgraph.json")
    thread_id: str = Field(description="ID do thread para checkpointer: phone:agent_id")
    incoming_message: str
    media_url: str | None = None
    media_type: str | None = None
    normalized_input: str | None = None
    media_processing_status: str | None = None
    media_processing_error: str | None = None
    status: MessageStatus = MessageStatus.QUEUED
    process_after: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    lease_until: datetime | None = None
    response: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None
