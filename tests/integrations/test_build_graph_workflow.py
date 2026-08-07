"""Testes de integração de ``ensure_user_node`` e ``finalize_response``.

Cobrem a regra de "boas-vindas só na primeira mensagem da vida do usuário"
sem invocar o roteador LLM nem os agentes de cada branch (que exigem chaves
de API e prompts registrados indisponíveis em ambiente de teste). Exigem um
Postgres acessível em ``settings.database_url`` com as migrations aplicadas
(identidade por ``(channel, external_user_id)``); quando o banco não responde,
o módulo inteiro é pulado.

Rodar só estes:
    uv run pytest -m db tests/integrations/test_build_graph_workflow.py
"""

from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio

from financial_agent.agent.build_graph_workflow import (
    _WELCOME_PREFIX,
    ensure_user_node,
    finalize_response,
)
from financial_agent.agent.state_graph import GraphState
from shared.config import settings
from shared.db import close_pool, connection

pytestmark = pytest.mark.db


async def _database_is_available() -> bool:
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, connect_timeout=3
        )
    except Exception:
        return False

    await conn.close()
    return True


@pytest_asyncio.fixture(autouse=True)
async def require_database():
    if not await _database_is_available():
        pytest.skip(f"Postgres indisponível em {settings.database_url}")
    yield
    await close_pool()


@pytest_asyncio.fixture
async def fresh_identity():
    """Par (channel, phone_number) nunca visto, apagado ao final do teste."""
    suffix = uuid4().hex[:10]
    channel = "whatsapp"
    phone_number = f"test-{suffix}"

    yield channel, phone_number

    async with connection() as conn:
        await conn.execute(
            'DELETE FROM "user" WHERE channel = %s AND external_user_id = %s',
            (channel, phone_number),
        )


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _minimal_state(channel: str, phone_number: str) -> GraphState:
    """Estado mínimo pré-``ensure_user_node``, só com o que o nó exige.

    Os campos obrigatórios ``user_id``/``user_name``/``user_timezone`` ainda
    não existem nesse ponto do grafo real (é o próprio nó que os preenche),
    então o dict é deliberadamente incompleto — o ``cast`` reflete isso sem
    inventar valores que a execução real nunca teria.
    """
    return cast(
        GraphState,
        {
            "messages": [],
            "phone_number": phone_number,
            "channel": channel,
        },
    )


async def test_ensure_user_node_creates_new_user_and_flags_it(fresh_identity):
    channel, phone_number = fresh_identity
    state = _minimal_state(channel, phone_number)

    result = await ensure_user_node(state)

    assert result["is_new_user"] is True
    assert isinstance(result["user_id"], str)
    assert _is_uuid(result["user_id"])


async def test_finalize_response_prefixes_welcome_for_new_user(fresh_identity):
    channel, phone_number = fresh_identity
    state = _minimal_state(channel, phone_number)
    ensure_result = await ensure_user_node(state)

    response_text = "algum texto de resposta"
    merged_state = cast(
        GraphState, {**state, **ensure_result, "response_text": response_text}
    )

    result = await finalize_response(merged_state)

    assert result["response_text"] is not None
    assert result["response_text"].startswith(_WELCOME_PREFIX)
    assert response_text in result["response_text"]


async def test_second_message_from_same_user_is_not_new_and_has_no_welcome(
    fresh_identity,
):
    channel, phone_number = fresh_identity
    state = _minimal_state(channel, phone_number)

    first_result = await ensure_user_node(state)
    assert first_result["is_new_user"] is True

    second_result = await ensure_user_node(state)
    assert second_result["is_new_user"] is False

    response_text = "algum texto de resposta"
    merged_state = cast(
        GraphState, {**state, **second_result, "response_text": response_text}
    )

    finalized = await finalize_response(merged_state)

    assert finalized["response_text"] == response_text
