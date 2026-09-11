"""Registro append-only das consultas de relatório ainda não suportadas."""

from uuid import UUID

from shared.db import user_connection

_INSERT_UNSUPPORTED_QUERY = """
    INSERT INTO unsupported_report_query (
        user_id, raw_question, intent, normalized_question,
        source_message_id, reason
    ) VALUES (
        %(user_id)s, %(raw_question)s, %(intent)s, %(normalized_question)s,
        %(source_message_id)s, %(reason)s
    )
"""


async def insert_unsupported_query(
    user_id: str | UUID,
    raw_question: str,
    intent: str,
    normalized_question: str,
    source_message_id: str | UUID | None = None,
    reason: str | None = None,
) -> None:
    async with user_connection(str(user_id)) as conn:
        await conn.execute(
            _INSERT_UNSUPPORTED_QUERY,
            {
                "user_id": str(user_id),
                "raw_question": raw_question,
                "intent": intent,
                "normalized_question": normalized_question,
                "source_message_id": (
                    str(source_message_id) if source_message_id else None
                ),
                "reason": reason,
            },
        )
