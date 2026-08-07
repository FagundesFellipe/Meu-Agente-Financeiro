"""Consultas à tabela ``user``."""

import hashlib
from dataclasses import dataclass
from uuid import UUID

from shared.db import connection

_LOCK_USER = "SELECT pg_advisory_xact_lock(%s)"


def _lock_key(namespace: str, *parts: str) -> int:
    """Gera uma chave de lock determinística via SHA-256 para o namespace.

    Produz um inteiro signed 64-bit a partir dos primeiros 8 bytes do hash,
    compatível com ``pg_advisory_xact_lock(bigint)``.
    """
    payload = f"{namespace}:{':'.join(parts)}".encode()
    return int.from_bytes(
        hashlib.sha256(payload).digest()[:8],
        byteorder="big",
        signed=True,
    )


_SELECT_BY_CHANNEL = """
    SELECT id, channel, external_user_id, name, timezone, currency, onboarding_status
    FROM "user"
    WHERE channel = %(channel)s
      AND external_user_id = %(external_user_id)s
      AND deleted_at IS NULL
"""

_INSERT_USER = """
    INSERT INTO "user" (channel, external_user_id)
    VALUES (%(channel)s, %(external_user_id)s)
    RETURNING id, channel, external_user_id, name, timezone, currency, onboarding_status
"""


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Usuário identificado, com as preferências necessárias ao agente."""

    id: UUID
    channel: str
    external_user_id: str
    name: str | None
    timezone: str
    currency: str
    onboarding_status: str


def _to_record(row: dict) -> UserRecord:
    return UserRecord(
        id=row["id"],
        channel=row["channel"],
        external_user_id=row["external_user_id"],
        name=row["name"],
        timezone=row["timezone"],
        currency=row["currency"],
        onboarding_status=row["onboarding_status"],
    )


async def ensure_user(channel: str, external_user_id: str) -> tuple[UserRecord, bool]:
    """Resolve o usuário pelo canal, criando-o se ainda não existir.

    A identidade do usuário é ``(channel, external_user_id)`` diretamente na
    tabela ``user``. Um lock consultivo evita corrida entre requisições
    concorrentes do mesmo canal/usuário externo criando linhas duplicadas.

    ATENÇÃO: Usa ``connection()`` (genérica, sem RLS) porque o usuário
    ainda não foi identificado — esta função é o ponto de entrada que
    **cria** a identidade. Nunca deve ser chamada com ``user_connection``.

    Returns:
        Uma tupla ``(usuário, criado)`` — ``criado`` é ``True`` quando a linha
        foi inserida nesta chamada, ``False`` quando já existia.
    """
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute(
                _LOCK_USER, (_lock_key("user", channel, external_user_id),)
            )

            cur = await conn.execute(
                _SELECT_BY_CHANNEL,
                {"channel": channel, "external_user_id": external_user_id},
            )
            row = await cur.fetchone()
            if row is not None:
                return _to_record(row), False

            cur = await conn.execute(
                _INSERT_USER,
                {"channel": channel, "external_user_id": external_user_id},
            )
            row = await cur.fetchone()
            if row is None:  # pragma: no cover - RETURNING sempre devolve linha
                raise RuntimeError('INSERT em "user" não retornou linha')

            return _to_record(row), True
