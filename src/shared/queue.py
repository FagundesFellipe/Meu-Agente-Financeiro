"""Operações de fila no PostgresSQL

Módulo compartilhado entre API e Worker para manipular message_queue.
Suporta múltiplos canais: WhatsApp (Twilio) e Telegram.

Uso:
    from src.shared.queue import enqueue_or_buffer

    result = await enqueue_or_buffer(
        channel="whatsapp", phone_number="+55...", body="Gastei 20"
    )

"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog

from shared.db import connection as db_connection
from src.shared.repositories.queue import EnqueueResult, MessageQueue

logger = structlog.get_logger()

Channel = Literal["telegram", "whatsapp"]

_DEBOUNCEABLE_FILTER = "(media_url IS NULL OR media_type LIKE 'audio/%%')"


def _thread_id(channel: Channel, phone_number: str, agent_id: str) -> str:
    return f"{channel}:{phone_number}:{agent_id}"


def _lock_key(thread_id: str) -> int:
    return int.from_bytes(
        hashlib.sha256(thread_id.encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )


def _is_audio(media_type: str | None) -> bool:
    return (media_type or "").startswith("audio/")


async def enqueue_or_buffer(
    channel: Channel,
    phone_number: str,
    agent_id: str,
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
    to_number: str | None = None,
    message_id: str | None = None,
    buffer_seconds: float = 2.0,
) -> EnqueueResult:
    """Insere mensagem na fila ou agrupa com mensagem pendente (debounce).

    Regras de debounce:
    - Texto e áudio (media_type LIKE 'audio/%') fazem debounce.
    - Imagem e demais mídias entram imediatamente na fila.
    - Antes de inserir mídia não-debounceable, flush de texto/áudio pendentes
      do mesmo phone+agent para garantir ordenação correta no worker.
    - Concorrência protegida por pg_advisory_xact_lock em transação explícita.

    Limitação conhecida: NumMedia > 1 no mesmo webhook fica fora do escopo.

    Args:
        channel: Canal de origem da mensagem ("telegram" ou "whatsapp").
        phone_number: ID do usuário (E.164 p/ WhatsApp, chat_id p/ Telegram).
        agent_id: ID do agente que vai processar.
        body: Texto da mensagem.
        media_url: URL de mídia anexada (opcional).
        media_type: MIME type da mídia (opcional).
        to_number: Número destinatário (opcional).
        message_id: ID externo da mensagem, ex: Twilio MessageSid (opcional).
        buffer_seconds: Segundos de debounce. Default: 2.0.

    Returns:
        EnqueueResult com message_id e se foi buffered.
    """
    thread_id = _thread_id(channel, phone_number, agent_id)
    is_debounceable = media_url is None or _is_audio(media_type)
    lock_key = _lock_key(thread_id)

    async with db_connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

            if not is_debounceable:
                # Imagem ou outra mídia não-debounceable:
                # flush de texto e áudio pendentes, depois inserção imediata.
                flushed = await conn.execute(
                    f"""
                    UPDATE message_queue
                    SET process_after = NOW(),
                        updated_at = NOW()
                    WHERE phone_number = %s
                      AND channel = %s
                      AND status = 'queued'
                      AND process_after > NOW()
                      AND {_DEBOUNCEABLE_FILTER}
                    """,
                    (phone_number, channel),
                )
                if flushed.rowcount and flushed.rowcount > 0:
                    logger.info(
                        "debounceable_flushed_for_media",
                        channel=channel,
                        phone=phone_number,
                        agent_id=agent_id,
                        flushed_count=flushed.rowcount,
                    )

                cursor = await conn.execute(
                    """
                    INSERT INTO message_queue
                        (message_id, phone_number, to_number, channel, agent_id,
                         thread_id, incoming_message, media_url, media_type,
                         process_after)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id
                    """,
                    (
                        message_id,
                        phone_number,
                        to_number,
                        channel,
                        agent_id,
                        thread_id,
                        body,
                        media_url,
                        media_type,
                    ),
                )
                row = await cursor.fetchone()
                assert row is not None
                new_id = row["id"]

                logger.info(
                    "message_enqueued",
                    channel=channel,
                    message_id=new_id,
                    phone=phone_number,
                    agent_id=agent_id,
                )
                return EnqueueResult(message_id=new_id, is_buffered=False)

            # Texto ou áudio: debounce normal.
            process_after = datetime.now(UTC) + timedelta(seconds=buffer_seconds)

            cursor = await conn.execute(
                f"""
                SELECT id, incoming_message, media_url, media_type
                FROM message_queue
                WHERE phone_number = %s
                  AND channel = %s
                  AND status = 'queued'
                  AND process_after > NOW()
                  AND {_DEBOUNCEABLE_FILTER}
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (phone_number, channel),
            )
            existing = await cursor.fetchone()

            if existing:
                existing_id = existing["id"]
                existing_body = existing["incoming_message"]
                new_body = f"{existing_body}\n{body}"

                # Se a nova mensagem tem mídia e a existente não,
                # promove a mídia (ex.: texto pendente + áudio chega).
                update_media_url = existing["media_url"]
                update_media_type = existing["media_type"]
                if media_url is not None and update_media_url is None:
                    update_media_url = media_url
                    update_media_type = media_type

                await conn.execute(
                    """
                    UPDATE message_queue
                    SET incoming_message = %s,
                        media_url = %s,
                        media_type = %s,
                        process_after = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        new_body,
                        update_media_url,
                        update_media_type,
                        process_after,
                        existing_id,
                    ),
                )

                logger.info(
                    "message_buffered",
                    channel=channel,
                    message_id=existing_id,
                    phone=phone_number,
                    agent_id=agent_id,
                )
                return EnqueueResult(message_id=existing_id, is_buffered=True)

            cursor = await conn.execute(
                """
                INSERT INTO message_queue
                    (message_id, phone_number, to_number, channel, agent_id,
                     thread_id, incoming_message, media_url, media_type, process_after)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    message_id,
                    phone_number,
                    to_number,
                    channel,
                    agent_id,
                    thread_id,
                    body,
                    media_url,
                    media_type,
                    process_after,
                ),
            )
            row = await cursor.fetchone()
            assert row is not None
            new_id = row["id"]

            logger.info(
                "message_enqueued",
                channel=channel,
                message_id=new_id,
                phone=phone_number,
                agent_id=agent_id,
            )
            return EnqueueResult(message_id=new_id, is_buffered=False)


async def claim_next(lease_seconds: int = 60) -> MessageQueue | None:
    """Busca e reserva a próxima mensagem pronta para o processamento

    Usa FOR UPDATE SKIP LOCKED para concorrência segura entre múltiplos workers.
    Só retorna mensagens após debaunce concluído e número de tentativas ainda válidas.

    Return:
        MessageQueue se houver mensagem disponível, None caso contrário.
    """

    lease_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)

    async with db_connection() as conn:
        async with conn.transaction():
            await conn.execute("""
                UPDATE message_queue
                SET status = 'failed',
                    error = COALESCE(
                        error,
                        'Processing lease expired after max attempts'
                    ),
                    processed_at = NOW(),
                    updated_at = NOW()
                WHERE status = 'processing'
                    AND lease_until IS NOT NULL
                    AND lease_until <= NOW()
                    AND attempts >= max_attempts
                """)

            cursor = await conn.execute(
                """
                UPDATE message_queue
                SET status = 'processing',
                    lease_until = %s,
                    attempts = attempts + 1,
                    updated_at = NOW()
                WHERE id = (
                    SELECT id FROM message_queue
                    WHERE (
                        status = 'queued'
                        AND process_after <= NOW()
                        AND attempts < max_attempts
                    )
                    OR (
                        status = 'processing'
                        AND lease_until IS NOT NULL
                        AND lease_until <= NOW()
                        AND attempts < max_attempts
                    )
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, message_id, phone_number, to_number, channel,
                          agent_id, thread_id,
                          incoming_message, media_url, media_type,
                          normalized_input,
                          media_processing_status,
                          media_processing_error,
                          status,
                          process_after, attempts, max_attempts, lease_until,
                          response, error, created_at, updated_at, processed_at
                """,
                (lease_until,),
            )
            row = await cursor.fetchone()

            if row is None:
                return None

            message = MessageQueue(
                id=row["id"],
                message_id=row["message_id"],
                phone_number=row["phone_number"],
                to_number=row["to_number"],
                channel=row["channel"],
                agent_id=row["agent_id"],
                thread_id=row["thread_id"],
                incoming_message=row["incoming_message"],
                media_url=row["media_url"],
                media_type=row["media_type"],
                normalized_input=row["normalized_input"],
                media_processing_status=row["media_processing_status"],
                media_processing_error=row["media_processing_error"],
                status=row["status"],
                process_after=row["process_after"],
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
                lease_until=row["lease_until"],
                response=row["response"],
                error=row["error"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                processed_at=row["processed_at"],
            )

    logger.info(
        "message_claimed",
        message_id=message.id,
        phone=message.phone_number,
        agent_id=message.agent_id,
        attempt=message.attempts,
    )

    return message


async def mark_done(
    message_id: int,
    response: str,
    normalized_input: str | None = None,
    media_processing_status: str | None = None,
    media_processing_error: str | None = None,
) -> None:
    """Marca a mensagem como concluída com sucesso"""

    async with db_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'done',
                    response = %s,
                    normalized_input = COALESCE(%s, normalized_input),
                    media_processing_status = COALESCE(%s, media_processing_status),
                    media_processing_error = COALESCE(%s, media_processing_error),
                    processed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    response,
                    normalized_input,
                    media_processing_status,
                    media_processing_error,
                    message_id,
                ),
            )

    logger.info("message_done", message_id=message_id)


async def mark_failed(message_id: int, error: str) -> None:
    """Marca mensagem como falha.

    Se ainda houver tentativas restantes volta para a fila.

    Args:
        message_id: ID da mensagem na fila.
        error: Descrição do erro.
    """

    async with db_connection() as conn:
        async with conn.transaction():
            _row = await conn.execute(
                "SELECT attempts, max_attempts FROM message_queue WHERE id = %s",
                (message_id,),
            )

            row = await _row.fetchone()

            if row and row["attempts"] < row["max_attempts"]:
                backoff_seconds = row["attempts"] * 5
                next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)

                await conn.execute(
                    """
                    UPDATE message_queue
                    SET status = 'queued',
                        error = %s,
                        lease_until = NULL,
                        process_after = NOW() + make_interval(secs => %s),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (error, backoff_seconds, message_id),
                )
                logger.warning(
                    "message_retry",
                    message_id=message_id,
                    attempt=row["attempts"],
                    max_attempts=row["max_attempts"],
                    backoff_seconds=backoff_seconds,
                    next_retry_at=next_retry_at.isoformat(),
                    error=error,
                )

            else:
                await conn.execute(
                    """
                    UPDATE message_queue
                    SET status = 'failed',
                        error = %s,
                        processed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (error, message_id),
                )
                logger.error(
                    "message_failed",
                    message_id=message_id,
                    error=error,
                )


async def upsert_conversation(
    phone_number: str, channel: Channel, agent_id: str, last_message: str
) -> None:
    """
    Atualiza ou cria registro de conversa.

    Usado após cada mensagem processada para manter o histórico
    de conversas atualizado (para o painel admin).

    Args:
        pool: Pool de conexões do psycopg.
        phone_number: Telefone do remetente.
        agent_id: ID do agente.
        last_message: Última mensagem processada.
    """

    thread_id = _thread_id(
        channel=channel, phone_number=phone_number, agent_id=agent_id
    )

    async with db_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO conversations (
                    phone_number, agent_id, thread_id,
                    last_message, last_message_at, message_count)
                VALUES (%s, %s, %s, %s, NOW(), 1)
                ON CONFLICT (phone_number, agent_id) WHERE user_id IS NULL
                DO UPDATE SET
                    last_message = EXCLUDED.last_message,
                    last_message_at = NOW(),
                    message_count = conversations.message_count + 1,
                    updated_at = NOW()
                """,
                (phone_number, agent_id, thread_id, last_message),
            )
