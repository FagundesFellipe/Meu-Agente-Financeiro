"""Fluxos seguros de pendências sem rede ou banco real."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from financial_agent.agent import build_graph_workflow as workflow_module
from financial_agent.agent.build_graph_workflow import (
    expire_pending_expenses,
    route_after_pending_expiration,
    route_after_pending_resolution,
)
from financial_agent.agent.ReAct import add_new_expenses_agent as add_module
from financial_agent.agent.ReAct import resolve_pending_expenses_agent as resolve_module
from financial_agent.agent.ReAct.add_new_expenses_agent import add_new_expenses
from financial_agent.agent.ReAct.resolve_pending_expenses_agent import (
    PendingResolutionDecision,
    resolve_pending_expenses,
)
from financial_agent.agent.state_graph import (
    AddExpensesResult,
    ExtractedExpense,
    GraphState,
    PendingExpense,
)
from shared.repositories.categories import CategoryRecord
from shared.repositories.expenses import ExpenseRecord

TZ = "America/Sao_Paulo"
NOW = datetime(2026, 8, 3, 14, 20, tzinfo=ZoneInfo(TZ))
FOOD_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def categories() -> list[CategoryRecord]:
    return [
        CategoryRecord(FOOD_ID, "Alimentação", "alimentacao", "Restaurantes", False),
        CategoryRecord(OTHER_ID, "Outros gastos", "outros_gastos", "Diversos", False),
    ]


def extracted(**overrides: object) -> ExtractedExpense:
    payload: dict[str, object] = {
        "description": "almoço",
        "amount_raw": "35",
        "installments": None,
        "amount_is_total": False,
        "date_hint": None,
        "time_hint": None,
        "payment_method_hint": None,
        "category_hint": "Alimentação",
        "confidence": 0.95,
    }
    payload.update(overrides)
    return ExtractedExpense(**payload)


def pending(**overrides: object) -> PendingExpense:
    payload: dict[str, object] = {
        "id": "geladeira-pendente",
        "description": "geladeira",
        "amount_raw": "5000",
        "amount_is_total": True,
        "missing_fields": ["installments"],
        "clarification_message": "Em quantas vezes foi a geladeira?",
        "created_at": NOW,
    }
    payload.update(overrides)
    return PendingExpense(**payload)


def state(**overrides: object) -> GraphState:
    payload: dict[str, object] = {
        "messages": [HumanMessage(content="Pizzaria 89,30 e geladeira 5000 parcelada")],
        "phone_number": "5535999228811",
        "channel": "telegram",
        "message_id": "mensagem-original",
        "user_id": str(uuid4()),
        "user_name": None,
        "user_timezone": TZ,
    }
    payload.update(overrides)
    return payload  # type: ignore[return-value]


@pytest.fixture
def stub_add_node(monkeypatch: pytest.MonkeyPatch, categories: list[CategoryRecord]):
    persisted: dict[str, object] = {}

    async def fake_categories(_: str) -> list[CategoryRecord]:
        return categories

    async def fake_insert(
        user_id: str, expenses: list, source_message_id: str | None = None
    ) -> list[ExpenseRecord]:
        del user_id
        persisted["source_message_id"] = source_message_id
        persisted["expenses"] = expenses
        return [
            ExpenseRecord(
                id=uuid4(),
                amount=expense.amount,
                description=expense.description,
                original_description=expense.original_description,
                payment_method=expense.payment_method,
                occurred_at=expense.occurred_at,
                category_id=expense.category_id,
                category_name=expense.category_name,
                installment_number=expense.installment_number,
                total_installments=expense.total_installments,
            )
            for expense in expenses
        ]

    monkeypatch.setattr(add_module, "list_available_categories", fake_categories)
    monkeypatch.setattr(add_module, "insert_expenses", fake_insert)
    monkeypatch.setattr(add_module.tools_calendar, "user_now", lambda _: NOW)

    def set_extraction(result: AddExpensesResult) -> None:
        async def fake_extract(_: GraphState, __: object) -> AddExpensesResult:
            return result

        monkeypatch.setattr(add_module, "_extract", fake_extract)

    persisted["set_extraction"] = set_extraction
    return persisted


async def test_installment_without_count_creates_only_a_pending_expense(stub_add_node):
    stub_add_node["set_extraction"](
        AddExpensesResult(
            pending_expenses=[
                pending(id=None, created_at=None),
            ]
        )
    )

    result = await add_new_expenses(state())

    assert "expenses" not in stub_add_node
    assert len(result["pending_expenses"]) == 1
    assert result["pending_expenses"][0].id is not None
    assert result["pending_expenses"][0].created_at == NOW
    assert "quantas vezes" in result["response_text"].lower()


async def test_clear_pizzeria_expense_is_saved_without_confirmation_question(
    stub_add_node,
):
    stub_add_node["set_extraction"](
        AddExpensesResult(
            expenses=[
                extracted(description="pizzaria", amount_raw="89,30"),
            ]
        )
    )

    result = await add_new_expenses(state())

    assert len(stub_add_node["expenses"]) == 1
    assert result["pending_expenses"] == []
    assert "Anotado" in result["response_text"]


async def test_mixed_message_saves_only_the_clear_expense(stub_add_node):
    stub_add_node["set_extraction"](
        AddExpensesResult(
            expenses=[
                extracted(
                    description="pizzaria",
                    amount_raw="89,30",
                    source_start=0,
                    source_end=14,
                    source_text="Pizzaria 89,30",
                )
            ],
            pending_expenses=[
                pending(
                    source_start=17,
                    source_end=41,
                    source_text="geladeira 5000 parcelada",
                )
            ],
        )
    )

    result = await add_new_expenses(state())

    assert len(stub_add_node["expenses"]) == 1
    assert stub_add_node["expenses"][0].description == "pizzaria"
    assert len(result["pending_expenses"]) == 1
    assert "Anotado" in result["response_text"]
    assert "quantas vezes" in result["response_text"].lower()


async def test_new_clear_expense_preserves_an_existing_pending_expense(stub_add_node):
    existing = pending(id="persistente")
    stub_add_node["set_extraction"](AddExpensesResult(expenses=[extracted()]))

    result = await add_new_expenses(state(pending_expenses=[existing]))

    assert len(stub_add_node["expenses"]) == 1
    assert result["pending_expenses"] == [existing]
    assert "Anotado" in result["response_text"]
    assert "quantas vezes" not in result["response_text"].lower()


async def test_missing_description_also_marks_category_as_missing(stub_add_node):
    """Categoria de um item desconhecido nunca pode ser tratada como confirmada."""
    stub_add_node["set_extraction"](
        AddExpensesResult(
            pending_expenses=[
                PendingExpense(
                    amount_raw="120",
                    missing_fields=["description"],
                    clarification_message="O que você comprou por R$120?",
                )
            ]
        )
    )

    result = await add_new_expenses(state())

    created = result["pending_expenses"][0]
    assert created.missing_fields == ["description", "category"]
    assert created.category_hint is None


async def test_inconsistent_clarification_never_persists_clear_expenses(stub_add_node):
    stub_add_node["set_extraction"](
        AddExpensesResult(
            expenses=[extracted()],
            needs_clarification=True,
            clarification_message="Qual gasto está pendente?",
        )
    )

    result = await add_new_expenses(state())

    assert "expenses" not in stub_add_node
    assert "não consegui identificar" in result["response_text"].lower()


async def test_overlapping_clear_and_pending_item_never_persists(stub_add_node):
    stub_add_node["set_extraction"](
        AddExpensesResult(
            expenses=[
                extracted(
                    description="geladeira Samsung",
                    amount_raw="5000",
                    source_start=0,
                    source_end=41,
                    source_text="Pizzaria 89,30 e geladeira 5000 parcelada",
                )
            ],
            pending_expenses=[
                pending(
                    source_start=0,
                    source_end=41,
                    source_text="Pizzaria 89,30 e geladeira 5000 parcelada",
                )
            ],
        )
    )

    result = await add_new_expenses(state())

    assert "expenses" not in stub_add_node
    assert "não consegui identificar" in result["response_text"].lower()


async def test_disjoint_fragments_of_one_item_never_persist(stub_add_node):
    stub_add_node["set_extraction"](
        AddExpensesResult(
            expenses=[
                extracted(
                    description="geladeira",
                    amount_raw="5000",
                    source_start=0,
                    source_end=14,
                    source_text="geladeira 5000",
                )
            ],
            pending_expenses=[
                pending(
                    source_start=15,
                    source_end=24,
                    source_text="parcelada",
                )
            ],
        )
    )

    result = await add_new_expenses(
        state(messages=[HumanMessage(content="geladeira 5000 parcelada")])
    )

    assert "expenses" not in stub_add_node
    assert "não consegui identificar" in result["response_text"].lower()


@pytest.fixture
def stub_pending_resolver(monkeypatch: pytest.MonkeyPatch, categories):
    calls: list[str | None] = []
    saved_by_message: dict[str | None, list[ExpenseRecord]] = {}

    async def fake_categories(_: str) -> list[CategoryRecord]:
        return categories

    async def fake_insert(
        user_id: str, expenses: list, source_message_id: str | None = None
    ) -> list[ExpenseRecord]:
        del user_id
        calls.append(source_message_id)
        if source_message_id in saved_by_message:
            return saved_by_message[source_message_id]
        records = [
            ExpenseRecord(
                id=uuid4(),
                amount=expense.amount,
                description=expense.description,
                original_description=expense.original_description,
                payment_method=expense.payment_method,
                occurred_at=expense.occurred_at,
                category_id=expense.category_id,
                category_name=expense.category_name,
                installment_number=expense.installment_number,
                total_installments=expense.total_installments,
            )
            for expense in expenses
        ]
        saved_by_message[source_message_id] = records
        return records

    monkeypatch.setattr(resolve_module, "list_available_categories", fake_categories)
    monkeypatch.setattr(resolve_module, "insert_expenses", fake_insert)
    monkeypatch.setattr(resolve_module.tools_calendar, "user_now", lambda _: NOW)
    return {"calls": calls, "saved_by_message": saved_by_message}, monkeypatch


async def test_complementary_message_creates_installments_once(stub_pending_resolver):
    tracker, monkeypatch = stub_pending_resolver

    async def completed(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(
            status="completed",
            expense=extracted(
                description="geladeira",
                amount_raw="5000",
                installments=3,
                amount_is_total=True,
                category_hint=None,
            ),
        )

    monkeypatch.setattr(resolve_module, "_resolve_one_pending_expense", completed)
    complementary_state = state(
        messages=[HumanMessage(content="em 3 vezes")],
        message_id="mensagem-complementar",
        pending_expenses=[pending()],
    )

    first = await resolve_pending_expenses(complementary_state)
    second = await resolve_pending_expenses(complementary_state)

    assert len(first["expense_details"]) == 3
    assert len(second["expense_details"]) == 3
    assert tracker["calls"] == ["mensagem-complementar", "mensagem-complementar"]
    assert len(tracker["saved_by_message"]) == 1
    assert len(tracker["saved_by_message"]["mensagem-complementar"]) == 3
    assert "geladeira" in first["response_text"]


async def test_new_expense_is_delegated_without_removing_pending_expenses(
    stub_pending_resolver,
):
    _, monkeypatch = stub_pending_resolver

    async def new_expense(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(status="new_expense")

    monkeypatch.setattr(resolve_module, "_resolve_one_pending_expense", new_expense)

    active_pending = [pending()]
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="Gastei 89 na pizzaria")],
            pending_expenses=active_pending,
        )
    )

    assert result["pending_expenses"] == active_pending
    assert result["pending_expense_resolution_route"] == "add_new_expenses_agent"
    assert "response_text" not in result


async def test_amount_response_completes_the_pending_expense_without_new_draft(
    stub_pending_resolver,
):
    tracker, monkeypatch = stub_pending_resolver
    amount_pending = pending(
        amount_raw=None,
        installments=10,
        amount_is_total=False,
        category_hint="Alimentação",
        missing_fields=["amount"],
    )

    async def completed_amount(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(
            status="completed",
            expense=extracted(
                description="geladeira",
                amount_raw="3499",
                installments=10,
                amount_is_total=False,
                category_hint="Alimentação",
            ),
        )

    monkeypatch.setattr(
        resolve_module, "_resolve_one_pending_expense", completed_amount
    )
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="Foi de 3499")],
            message_id="mensagem-complementar",
            pending_expenses=[amount_pending],
        )
    )

    assert len(tracker["saved_by_message"]["mensagem-complementar"]) == 10
    assert result["pending_expenses"] == []
    assert result["pending_expense_resolution_route"] == "finalize_response"


async def test_completed_pending_includes_the_next_pending_question(
    stub_pending_resolver,
):
    _, monkeypatch = stub_pending_resolver
    completed_pending = pending(id="concluida")
    remaining_pending = pending(
        id="restante",
        clarification_message="Qual foi o valor do mercado?",
    )

    async def decide(current: PendingExpense, *_: object) -> PendingResolutionDecision:
        if current.id == "concluida":
            return PendingResolutionDecision(
                status="completed",
                expense=extracted(
                    description="geladeira",
                    amount_raw="5000",
                    installments=3,
                    amount_is_total=True,
                    category_hint=None,
                ),
            )
        return PendingResolutionDecision(status="not_applicable")

    monkeypatch.setattr(resolve_module, "_resolve_one_pending_expense", decide)
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="em 3 vezes")],
            pending_expenses=[completed_pending, remaining_pending],
        )
    )

    assert result["pending_expenses"] == [remaining_pending]
    assert "Qual foi o valor do mercado?" in result["response_text"]


def test_active_pending_bypasses_llm_router():
    assert route_after_pending_expiration(state(pending_expenses=[pending()])) == (
        "resolve_pending_expenses_agent"
    )


def test_no_pending_uses_llm_router():
    assert route_after_pending_expiration(state()) == "llm_call_router"


def test_expired_pending_uses_resolver_to_send_expiration_response():
    assert (
        route_after_pending_expiration(
            state(
                expired_pending_expenses=[pending(created_at=NOW - timedelta(hours=24))]
            )
        )
        == "resolve_pending_expenses_agent"
    )


def test_new_expense_resolution_continues_to_add_expenses():
    assert (
        route_after_pending_resolution(
            state(pending_expense_resolution_route="add_new_expenses_agent")
        )
        == "add_new_expenses_agent"
    )


async def test_workflow_bypasses_router_for_active_pending_and_adds_new_expense(
    monkeypatch: pytest.MonkeyPatch,
):
    active_pending = [pending(created_at=None)]
    calls: list[str] = []

    async def ensure_user(_: GraphState) -> dict:
        return {
            "user_id": str(uuid4()),
            "user_name": None,
            "user_timezone": TZ,
            "is_new_user": False,
        }

    async def router(_: GraphState) -> dict:
        calls.append("router")
        return {"intention": "add_new_expenses"}

    async def resolve_pending(current: GraphState) -> dict:
        calls.append("resolver")
        assert current["pending_expenses"] == active_pending
        return {
            "pending_expense_resolution_route": "add_new_expenses_agent",
            "pending_expenses": active_pending,
        }

    async def add_expense(current: GraphState) -> dict:
        calls.append("add")
        current_message = current["messages"][-1].content
        if current_message == "Comprei uma geladeira":
            return {
                "pending_expenses": active_pending,
                "response_text": "Qual foi o valor da geladeira?",
            }

        assert current["pending_expenses"] == active_pending
        return {
            "pending_expenses": active_pending,
            "response_text": "Anotado: pizzaria — R$ 89.00 (Alimentação).",
        }

    monkeypatch.setattr(workflow_module, "ensure_user_node", ensure_user)
    monkeypatch.setattr(workflow_module, "llm_call_router", router)
    monkeypatch.setattr(workflow_module, "resolve_pending_expenses", resolve_pending)
    monkeypatch.setattr(workflow_module, "add_new_expenses", add_expense)

    compiled = workflow_module.build_workflow().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "pending-routing-test"}}

    await compiled.ainvoke(
        {
            "messages": [HumanMessage(content="Comprei uma geladeira")],
            "phone_number": "5535999228811",
            "channel": "telegram",
        },
        config=config,
    )
    result = await compiled.ainvoke(
        {
            "messages": [HumanMessage(content="Gastei 89 na pizzaria")],
            "phone_number": "5535999228811",
            "channel": "telegram",
        },
        config=config,
    )

    assert calls == ["router", "add", "resolver", "add"]
    assert result["pending_expenses"] == active_pending


async def test_workflow_resolves_amount_response_without_calling_add_expenses(
    monkeypatch: pytest.MonkeyPatch,
):
    active_pending = [pending(created_at=None, amount_raw=None, installments=10)]
    calls: list[str] = []

    async def ensure_user(_: GraphState) -> dict:
        return {
            "user_id": str(uuid4()),
            "user_name": None,
            "user_timezone": TZ,
            "is_new_user": False,
        }

    async def router(_: GraphState) -> dict:
        calls.append("router")
        return {"intention": "add_new_expenses"}

    async def resolve_pending(current: GraphState) -> dict:
        calls.append("resolver")
        assert current["messages"][-1].content == "Foi de 3499"
        assert current["pending_expenses"] == active_pending
        return {
            "pending_expense_resolution_route": "finalize_response",
            "pending_expenses": [],
            "response_text": "Anotado: geladeira — R$ 3499.00 (Moradia).",
        }

    async def add_expense(current: GraphState) -> dict:
        calls.append("add")
        if current["messages"][-1].content != "Comprei uma geladeira":
            raise AssertionError("resposta complementar não deve chamar o extrator")
        return {
            "pending_expenses": active_pending,
            "response_text": "Qual foi o valor da geladeira?",
        }

    monkeypatch.setattr(workflow_module, "ensure_user_node", ensure_user)
    monkeypatch.setattr(workflow_module, "llm_call_router", router)
    monkeypatch.setattr(workflow_module, "resolve_pending_expenses", resolve_pending)
    monkeypatch.setattr(workflow_module, "add_new_expenses", add_expense)

    compiled = workflow_module.build_workflow().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "pending-amount-routing-test"}}
    await compiled.ainvoke(
        {
            "messages": [HumanMessage(content="Comprei uma geladeira")],
            "phone_number": "5535999228811",
            "channel": "telegram",
        },
        config=config,
    )
    result = await compiled.ainvoke(
        {
            "messages": [HumanMessage(content="Foi de 3499")],
            "phone_number": "5535999228811",
            "channel": "telegram",
        },
        config=config,
    )

    assert calls == ["router", "add", "resolver"]
    assert result["pending_expenses"] == []


async def test_resolver_cannot_change_confirmed_pending_fields(stub_pending_resolver):
    tracker, monkeypatch = stub_pending_resolver

    async def altered_expense(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(
            status="completed",
            expense=extracted(
                description="televisão",
                amount_raw="1",
                installments=3,
                amount_is_total=False,
            ),
        )

    monkeypatch.setattr(resolve_module, "_resolve_one_pending_expense", altered_expense)
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="em 3 vezes")],
            message_id="mensagem-complementar",
            pending_expenses=[pending()],
        )
    )

    assert tracker["saved_by_message"] == {}
    assert result["pending_expenses"] == [pending()]


async def test_resolver_cannot_invent_confirmed_none_installments(
    stub_pending_resolver,
):
    tracker, monkeypatch = stub_pending_resolver
    amount_pending = pending(
        id="valor-pendente",
        amount_raw=None,
        amount_is_total=False,
        installments=None,
        missing_fields=["amount"],
    )

    async def invented_installments(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(
            status="completed",
            expense=extracted(
                description="geladeira",
                amount_raw="5000",
                installments=3,
                category_hint=None,
            ),
        )

    monkeypatch.setattr(
        resolve_module, "_resolve_one_pending_expense", invented_installments
    )
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="5000")],
            pending_expenses=[amount_pending],
        )
    )

    assert tracker["saved_by_message"] == {}
    assert result["pending_expenses"] == [amount_pending]


async def test_category_inferred_after_description_is_no_longer_blocked(
    stub_pending_resolver,
):
    """Regressão do loop infinito: categoria pode ser preenchida junto da descrição."""
    tracker, monkeypatch = stub_pending_resolver
    unknown_item_pending = pending(
        id="item-desconhecido",
        description=None,
        amount_raw="120",
        amount_is_total=False,
        category_hint=None,
        missing_fields=["description", "category"],
        clarification_message="O que você comprou por R$120?",
    )

    async def completed_with_category(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(
            status="completed",
            expense=extracted(
                description="Whey",
                amount_raw="120",
                category_hint="Alimentação",
            ),
        )

    monkeypatch.setattr(
        resolve_module, "_resolve_one_pending_expense", completed_with_category
    )
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="Whey")],
            message_id="mensagem-complementar",
            pending_expenses=[unknown_item_pending],
        )
    )

    assert tracker["saved_by_message"]["mensagem-complementar"]
    assert result["pending_expenses"] == []


async def test_expired_pending_expense_is_removed_before_routing(monkeypatch):
    monkeypatch.setattr(
        "financial_agent.agent.build_graph_workflow.tools_calendar.user_now",
        lambda _: NOW,
    )

    result = await expire_pending_expenses(
        state(pending_expenses=[pending(created_at=NOW - timedelta(hours=24))])
    )

    assert result["pending_expenses"] == []
    assert len(result["expired_pending_expenses"]) == 1


async def test_response_to_expired_pending_expense_requests_a_new_full_expense():
    result = await resolve_pending_expenses(
        state(expired_pending_expenses=[pending(created_at=NOW - timedelta(hours=24))])
    )

    assert "expirou" in result["response_text"].lower()
    assert "gasto completo" in result["response_text"].lower()


async def test_cancellation_removes_the_single_pending_expense_without_insert(
    monkeypatch,
):
    async def unexpected_insert(*_: object) -> list[ExpenseRecord]:
        raise AssertionError("cancelamento não pode persistir gasto")

    monkeypatch.setattr(resolve_module, "insert_expenses", unexpected_insert)

    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="desisto")],
            pending_expenses=[pending()],
        )
    )

    assert result["pending_expenses"] == []
    assert "cancelei" in result["response_text"].lower()


async def test_ambiguous_response_keeps_multiple_pending_expenses(
    stub_pending_resolver,
):
    _, monkeypatch = stub_pending_resolver

    async def not_applicable(*_: object) -> PendingResolutionDecision:
        return PendingResolutionDecision(status="not_applicable")

    monkeypatch.setattr(resolve_module, "_resolve_one_pending_expense", not_applicable)
    result = await resolve_pending_expenses(
        state(
            messages=[HumanMessage(content="sim")],
            pending_expenses=[pending(), pending(id="outra-pendente")],
        )
    )

    assert len(result["pending_expenses"]) == 2
    assert "mais de uma" in result["response_text"].lower()
