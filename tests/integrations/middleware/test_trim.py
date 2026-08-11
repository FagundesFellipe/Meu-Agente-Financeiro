"""Testes unitários para as estratégias de trim do middleware."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from financial_agent.agent.middleware.trim import (
    create_trim_node,
    trim_messages_by_turns,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _h(content: str, msg_id: str | None = None) -> HumanMessage:
    """Cria HumanMessage com id explícito para garantir previsibilidade."""
    msg = HumanMessage(content=content)
    msg.id = msg_id or content
    return msg


def _a(content: str) -> AIMessage:
    msg = AIMessage(content=content)
    msg.id = content
    return msg


def _t(content: str) -> ToolMessage:
    msg = ToolMessage(content=content, tool_call_id="tc1")
    msg.id = content
    return msg


def _ids(messages):
    """Extrai os ids de uma lista de mensagens."""
    return [m.id for m in messages]


def _contents(messages):
    """Extrai os conteúdos de uma lista de mensagens."""
    return [m.content for m in messages]


def _make_state(*messages):
    """Constrói um GraphState mínimo para testes de nó."""
    return {
        "messages": list(messages),
        "phone_number": "+5511999999999",
        "channel": "telegram",
        "user_id": "user-1",
        "user_name": None,
        "user_timezone": "America/Sao_Paulo",
    }


# ---------------------------------------------------------------------------
# trim_messages_by_turns
# ---------------------------------------------------------------------------


def test_returns_all_when_empty():
    assert trim_messages_by_turns([], keep_turns=5) == []


def test_returns_all_when_fewer_turns_than_limit():
    messages = [_h("oi")]
    assert trim_messages_by_turns(messages, keep_turns=3) == messages


def test_returns_all_when_exactly_at_limit():
    messages = [_h("msg 1"), _h("msg 2"), _h("msg 3")]
    assert trim_messages_by_turns(messages, keep_turns=3) == messages


def test_trims_oldest_turns_keeping_n_recent():
    messages = [
        _h("primeira"),
        _h("segunda"),
        _h("terceira"),
        _h("quarta"),
        _h("quinta"),
    ]

    result = trim_messages_by_turns(messages, keep_turns=3)

    assert _contents(result) == ["terceira", "quarta", "quinta"]


def test_counts_turns_by_human_message_not_total_message_count():
    """Um turno pode ter várias mensagens (AIMessage, ToolMessage) após o Human."""
    messages = [
        _h("oi"),
        _a("olá!"),
        _t("result"),
        _a("segue resultado"),
        _h("obrigado"),
        _a("de nada!"),
    ]

    result = trim_messages_by_turns(messages, keep_turns=1)

    # 2 turnos: [h a t a] + [h a]. keep_turns=1 → só o último
    assert _contents(result) == ["obrigado", "de nada!"]


def test_keep_turns_one_keeps_only_last_turn():
    messages = [_h("a"), _h("b"), _h("c")]

    result = trim_messages_by_turns(messages, keep_turns=1)

    assert _contents(result) == ["c"]


def test_returns_unchanged_when_no_human_messages():
    messages = [_a("resposta automática")]
    assert trim_messages_by_turns(messages, keep_turns=3) == messages


def test_does_not_break_turns_in_the_middle():
    """O corte deve preservar turnos inteiros — nunca cortar no meio."""
    messages = [
        _h("msg1"),
        _a("resp1"),
        _h("msg2"),
        _a("resp2a"),
        _a("resp2b"),
        _t("tool"),
        _h("msg3"),
        _a("resp3"),
        _h("msg4"),
    ]

    result = trim_messages_by_turns(messages, keep_turns=2)

    assert _contents(result) == ["msg3", "resp3", "msg4"]


def test_default_keep_turns_is_three():
    messages = [
        _h("a"),
        _h("b"),
        _h("c"),
        _h("d"),
        _h("e"),
        _h("f"),
        _h("g"),
    ]

    result = trim_messages_by_turns(messages)

    assert _contents(result) == ["e", "f", "g"]


# ---------------------------------------------------------------------------
# create_trim_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_returns_empty_when_under_limit():
    node = create_trim_node(keep_turns=5)
    state = _make_state(_h("única mensagem", msg_id="1"))

    result = await node(state)

    assert result == {}


@pytest.mark.asyncio
async def test_node_returns_empty_when_exactly_at_limit():
    node = create_trim_node(keep_turns=2)
    state = _make_state(_h("msg 1", msg_id="1"), _h("msg 2", msg_id="2"))

    result = await node(state)

    assert result == {}


@pytest.mark.asyncio
async def test_node_returns_removemessage_for_old_messages():
    node = create_trim_node(keep_turns=2)
    messages = [
        _h("antiga 1", msg_id="1"),
        _h("antiga 2", msg_id="2"),
        _h("recente 1", msg_id="3"),
        _h("recente 2", msg_id="4"),
    ]
    state = _make_state(*messages)

    result = await node(state)

    assert "messages" in result
    removals = result["messages"]
    assert len(removals) == 2
    assert {r.id for r in removals} == {"1", "2"}
    for r in removals:
        assert isinstance(r, RemoveMessage)


@pytest.mark.asyncio
async def test_node_removes_correct_turns_with_mixed_messages():
    """Garante que mensagens não-Human do turno removido também são deletadas."""
    node = create_trim_node(keep_turns=1)
    messages = [
        _h("primeiro turno", msg_id="h1"),
        _a("resposta antiga"),
        _t("ferramenta"),
        _h("segundo turno — deve ficar", msg_id="h2"),
        _a("resposta recente"),
    ]
    state = _make_state(*messages)

    result = await node(state)

    removals = result["messages"]
    assert len(removals) == 3
    removed_ids = {r.id for r in removals}
    assert removed_ids == {"h1", "resposta antiga", "ferramenta"}


@pytest.mark.asyncio
async def test_node_removemessage_has_ids():
    """RemoveMessage sem id seria ignorado pelo reducer add_messages."""
    node = create_trim_node(keep_turns=1)
    state = _make_state(_h("antiga", msg_id="1"), _h("recente", msg_id="2"))

    result = await node(state)

    for r in result["messages"]:
        assert isinstance(r, RemoveMessage)
        assert r.id is not None


@pytest.mark.asyncio
async def test_node_with_messages_without_ids():
    """Mensagens sem id são puladas (não podemos removê-las)."""
    node = create_trim_node(keep_turns=1)

    h_no_id = HumanMessage(content="sem id")

    h_with_id = _h("com id", msg_id="keep-me")
    state = _make_state(h_no_id, h_with_id)

    result = await node(state)

    removals = result["messages"]
    # h_no_id está no bloco de remoção mas sem id → nenhum RemoveMessage
    assert len(removals) == 0


@pytest.mark.asyncio
async def test_node_skip_messages_without_id():
    """Mensagens sem id são ignoradas; as com id no mesmo bloco são removidas."""
    node = create_trim_node(keep_turns=2)

    h1 = _h("antiga com id", msg_id="h1")
    a1 = AIMessage(content="sem id")
    h2 = _h("recente 1", msg_id="h2")
    h3 = _h("recente 2", msg_id="h3")

    state = _make_state(h1, a1, h2, h3)
    result = await node(state)

    removed_ids = {r.id for r in result["messages"]}
    assert removed_ids == {"h1"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keep_turns", "expected_removed", "expected_kept"),
    [
        (1, 4, 1),
        (3, 2, 3),
        (10, 0, 5),
    ],
)
async def test_node_keeps_exactly_keep_turns(
    keep_turns: int, expected_removed: int, expected_kept: int
):
    total = 5
    messages = [_h(f"msg {i}", msg_id=f"msg-{i}") for i in range(total)]

    node = create_trim_node(keep_turns=keep_turns)
    state = _make_state(*messages)

    result = await node(state)

    if expected_removed == 0:
        assert result == {}
    else:
        assert len(result["messages"]) == expected_removed
        kept_count = total - len(result["messages"])
        assert kept_count == expected_kept
