"""Resolução, expiração e roteamento de pendências de gasto fixo.

Sem rede e sem banco: o agente de decisão é substituído por um dublê que
devolve uma ``PendingRecurringResolutionDecision`` fixa por rascunho.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import HumanMessage

from financial_agent.agent import build_graph_workflow as workflow_module
from financial_agent.agent.build_graph_workflow import (
    expire_pending_expenses,
    route_after_pending_expiration,
    route_after_pending_recurring_resolution,
)
from financial_agent.agent.ReAct import (
    resolve_pending_recurring_expenses_agent as resolve_module,
)
from financial_agent.agent.ReAct.resolve_pending_recurring_expenses_agent import (
    PendingRecurringResolutionDecision,
    build_pending_recurring_resolution_prompt,
    resolve_pending_recurring_expenses,
)
from financial_agent.agent.state_graph import (
    ExtractedRecurringExpense,
    GraphState,
    PendingExpense,
    PendingRecurringExpense,
)
from shared.repositories.categories import CategoryRecord
from shared.repositories.recurring_expenses import (
    InsertRecurringResult,
    RecurringExpenseRecord,
)

TZ = "America/Sao_Paulo"
NOW = datetime(2026, 8, 31, 14, 20, tzinfo=ZoneInfo(TZ))
SUBSCRIPTIONS_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def categories() -> list[CategoryRecord]:
    return [
        CategoryRecord(
            SUBSCRIPTIONS_ID, "Assinaturas", "assinaturas", "Streaming", False
        )
    ]


def pending(**overrides: object) -> PendingRecurringExpense:
    payload: dict[str, object] = {
        "id": "spotify-pendente",
        "description": "Spotify",
        "amount_raw": "21,90",
        "recurrence_day_hint": None,
        "category_hint": "Assinaturas",
        "missing_fields": ["recurrence_day"],
        "clarification_message": "Em que dia do mês a cobrança do Spotify acontece?",
        "created_at": NOW,
    }
    payload.update(overrides)
    return PendingRecurringExpense(**payload)


def completed_proposal(**overrides: object) -> ExtractedRecurringExpense:
    payload: dict[str, object] = {
        "description": "Spotify",
        "amount_raw": "21,90",
        "recurrence_day_hint": "dia 8",
        "starts_at_hint": None,
        "payment_method_hint": None,
        "category_hint": "Assinaturas",
        "confidence": 0.95,
    }
    payload.update(overrides)
    return ExtractedRecurringExpense(**payload)


def state(**overrides: object) -> GraphState:
    payload: dict[str, object] = {
        "messages": [HumanMessage(content="dia 8")],
        "phone_number": "5535999228811",
        "channel": "telegram",
        "message_id": "mensagem-de-resposta",
        "user_id": str(uuid4()),
        "user_name": None,
        "user_timezone": TZ,
        "pending_recurring_expenses": [pending()],
    }
    payload.update(overrides)
    return payload  # type: ignore[return-value]


@pytest.fixture
def stub_resolver(monkeypatch: pytest.MonkeyPatch, categories: list[CategoryRecord]):
    """Isola o nó: categorias, relógio, LLM e persistência viram dublês."""
    captured: dict[str, object] = {}

    async def fake_categories(_: str) -> list[CategoryRecord]:
        return categories

    async def fake_insert(
        user_id: str, recurring_expenses: list, source_message_id: str | None = None
    ) -> InsertRecurringResult:
        del user_id, source_message_id
        captured["persisted"] = recurring_expenses
        return InsertRecurringResult(
            inserted=[
                RecurringExpenseRecord(
                    id=uuid4(),
                    description=details.description,
                    amount=details.amount,
                    payment_method=details.payment_method,
                    recurrence_day=details.recurrence_day,
                    starts_at=details.starts_at,
                    ends_at=None,
                    category_id=details.category_id,
                    category_name=details.category_name,
                )
                for details in recurring_expenses
            ],
            duplicates=[],
        )

    monkeypatch.setattr(resolve_module, "list_available_categories", fake_categories)
    monkeypatch.setattr(resolve_module, "insert_recurring_expenses", fake_insert)
    monkeypatch.setattr(resolve_module.tools_calendar, "user_now", lambda _: NOW)

    def set_decisions(*decisions: PendingRecurringResolutionDecision) -> None:
        remaining = list(decisions)

        async def fake_decide(*_: object) -> PendingRecurringResolutionDecision:
            return remaining.pop(0)

        monkeypatch.setattr(
            resolve_module, "_resolve_one_pending_recurring_expense", fake_decide
        )

    captured["set_decisions"] = set_decisions
    return captured


# ---- TC-007 ----
async def test_answering_the_open_question_persists_the_rule(stub_resolver):
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(
            status="completed", recurring_expense=completed_proposal()
        )
    )

    result = await resolve_pending_recurring_expenses(state())

    persisted = stub_resolver["persisted"]
    assert len(persisted) == 1
    assert persisted[0].recurrence_day == 8
    assert persisted[0].amount == Decimal("21.90")
    assert result["pending_recurring_expenses"] == []
    assert result["pending_recurring_expense_resolution_route"] == "finalize_response"


# ---- TC-008 ----
async def test_cancelling_removes_the_draft_without_persisting(stub_resolver):
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(status="cancelled")
    )

    result = await resolve_pending_recurring_expenses(state())

    assert "persisted" not in stub_resolver
    assert result["pending_recurring_expenses"] == []
    assert "cancelei" in (result["response_text"] or "")


async def test_literal_cancellation_skips_the_llm_entirely(stub_resolver):
    """Uma pendência só e a palavra 'cancelar' não precisam de modelo."""
    result = await resolve_pending_recurring_expenses(
        state(messages=[HumanMessage(content="pode cancelar")])
    )

    assert "persisted" not in stub_resolver
    assert result["pending_recurring_expenses"] == []


# ---- TC-009 ----
async def test_a_brand_new_rule_reroutes_to_the_registration_node(stub_resolver):
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(status="new_recurring_expense")
    )

    result = await resolve_pending_recurring_expenses(
        state(messages=[HumanMessage(content="meu aluguel é 1500 todo dia 5")])
    )

    assert (
        result["pending_recurring_expense_resolution_route"]
        == "add_recurring_expenses_agent"
    )
    assert result["pending_recurring_expenses"] == [pending()]
    assert "response_text" not in result
    assert route_after_pending_recurring_resolution(result) == (  # type: ignore[arg-type]
        "add_recurring_expenses_agent"
    )


# ---- TC-010 ----
async def test_a_draft_older_than_the_ttl_expires(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(workflow_module.tools_calendar, "user_now", lambda _: NOW)
    expired = pending(created_at=NOW - timedelta(hours=25))
    active = pending(id="netflix-pendente", created_at=NOW - timedelta(hours=1))

    result = await expire_pending_expenses(
        state(pending_recurring_expenses=[expired, active], user_timezone=TZ)
    )

    assert result["expired_pending_recurring_expenses"] == [expired]
    assert result["pending_recurring_expenses"] == [active]


async def test_expired_draft_gets_the_expiration_message(stub_resolver):
    expired = pending(created_at=NOW - timedelta(hours=25))

    result = await resolve_pending_recurring_expenses(
        state(
            pending_recurring_expenses=[],
            expired_pending_recurring_expenses=[expired],
        )
    )

    assert "expirou" in (result["response_text"] or "")
    assert result["pending_recurring_expenses"] == []


# ---- TC-014 ----
def test_a_pending_expense_wins_over_a_pending_recurring_expense():  # CON-003
    pending_expense = PendingExpense(
        id="almoco",
        description="almoço",
        missing_fields=["amount"],
        clarification_message="Qual foi o valor do almoço?",
        created_at=NOW,
    )

    route = route_after_pending_expiration(
        state(
            pending_expenses=[pending_expense],
            pending_recurring_expenses=[pending()],
        )
    )

    assert route == "resolve_pending_expenses_agent"


def test_only_a_pending_recurring_expense_routes_to_its_own_resolver():
    assert (
        route_after_pending_expiration(state())
        == "resolve_pending_recurring_expenses_agent"
    )


def test_no_pending_at_all_goes_to_the_router():
    assert (
        route_after_pending_expiration(state(pending_recurring_expenses=[]))
        == "llm_call_router"
    )


# ---- CON-015 e guard de campos confirmados ----
async def test_two_actionable_decisions_apply_none_of_them(stub_resolver):
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(
            status="completed", recurring_expense=completed_proposal()
        ),
        PendingRecurringResolutionDecision(
            status="completed",
            recurring_expense=completed_proposal(description="Netflix"),
        ),
    )

    result = await resolve_pending_recurring_expenses(
        state(
            pending_recurring_expenses=[
                pending(),
                pending(id="netflix-pendente", description="Netflix"),
            ]
        )
    )

    assert "persisted" not in stub_resolver
    assert len(result["pending_recurring_expenses"]) == 2
    assert "mais de um gasto fixo" in (result["response_text"] or "")


async def test_a_proposal_that_rewrites_a_confirmed_field_is_rejected(stub_resolver):
    """O modelo não pode 'recomeçar' a extração a partir de uma resposta curta."""
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(
            status="completed", recurring_expense=completed_proposal(amount_raw="99")
        )
    )

    result = await resolve_pending_recurring_expenses(state())

    assert "persisted" not in stub_resolver
    assert result["pending_recurring_expenses"] == [pending()]
    assert result["response_text"] == pending().clarification_message


async def test_a_proposal_that_still_lacks_the_missing_field_is_rejected(stub_resolver):
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(
            status="completed",
            recurring_expense=completed_proposal(recurrence_day_hint=None),
        )
    )

    result = await resolve_pending_recurring_expenses(state())

    assert "persisted" not in stub_resolver
    assert result["pending_recurring_expenses"] == [pending()]


async def test_no_active_pending_asks_for_the_full_rule(stub_resolver):
    result = await resolve_pending_recurring_expenses(
        state(pending_recurring_expenses=[])
    )

    assert "gasto fixo pendente" in (result["response_text"] or "")


async def test_category_load_failure_repeats_the_open_question(
    stub_resolver, monkeypatch: pytest.MonkeyPatch
):
    async def exploding_categories(_: str) -> list[CategoryRecord]:
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(
        resolve_module, "list_available_categories", exploding_categories
    )

    result = await resolve_pending_recurring_expenses(state())

    assert result["pending_recurring_expenses"] == [pending()]
    assert result["response_text"] == pending().clarification_message


async def test_insert_failure_keeps_the_draft_and_the_open_question(
    stub_resolver, monkeypatch: pytest.MonkeyPatch
):
    async def exploding_insert(**_: object) -> InsertRecurringResult:
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(resolve_module, "insert_recurring_expenses", exploding_insert)
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(
            status="completed", recurring_expense=completed_proposal()
        )
    )

    result = await resolve_pending_recurring_expenses(state())

    assert result["pending_recurring_expenses"] == [pending()]
    assert "não consegui salvar" in (result["response_text"] or "").lower()
    assert result["clarification_message"] == pending().clarification_message


async def test_a_duplicate_found_on_resolution_is_reported_to_the_user(
    stub_resolver, monkeypatch: pytest.MonkeyPatch
):
    existing = RecurringExpenseRecord(
        id=uuid4(),
        description="Spotify",
        amount=Decimal("21.90"),
        payment_method="not_informed",
        recurrence_day=8,
        starts_at=date(2026, 1, 1),
        ends_at=None,
        category_id=SUBSCRIPTIONS_ID,
        category_name="Assinaturas",
    )

    async def fake_insert(**_: object) -> InsertRecurringResult:
        return InsertRecurringResult(inserted=[], duplicates=[existing])

    monkeypatch.setattr(resolve_module, "insert_recurring_expenses", fake_insert)
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(
            status="completed", recurring_expense=completed_proposal()
        )
    )

    result = await resolve_pending_recurring_expenses(state())

    assert "já tem Spotify" in (result["response_text"] or "")
    assert result["pending_recurring_expenses"] == []


async def test_completed_without_a_proposal_repeats_the_open_question(stub_resolver):
    stub_resolver["set_decisions"](
        PendingRecurringResolutionDecision(status="completed", recurring_expense=None)
    )

    result = await resolve_pending_recurring_expenses(state())

    assert "persisted" not in stub_resolver
    assert result["pending_recurring_expenses"] == [pending()]


def test_the_resolution_prompt_carries_only_the_allowed_context(categories):
    content = build_pending_recurring_resolution_prompt(
        pending(), NOW, categories
    ).content

    assert "CONTEXTO_DE_PENDENCIA" in content
    assert NOW.isoformat() in content
    assert "Spotify" in content and "Assinaturas" in content


def test_a_message_given_as_a_dict_is_read_the_same_way():
    """O grafo aceita mensagens como dict; o canal de cancelamento também."""
    assert resolve_module._text_of_message({"content": "cancelar"}) == "cancelar"
