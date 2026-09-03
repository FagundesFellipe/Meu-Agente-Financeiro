"""Fluxo de cadastro de gasto fixo sem rede e sem banco real.

O agente de extração é substituído por um dublê que devolve um
``AddRecurringExpensesResult`` fixo; nenhum teste aqui chama o OpenRouter.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import HumanMessage

from financial_agent.agent.ReAct import add_recurring_expenses_agent as add_module
from financial_agent.agent.ReAct.add_recurring_expenses_agent import (
    add_recurring_expenses,
    format_duplicate_message,
    format_recurring_confirmation,
    resolve_extracted_recurring_expenses,
)
from financial_agent.agent.state_graph import (
    AddRecurringExpensesResult,
    ExtractedRecurringExpense,
    GraphState,
    PendingRecurringExpense,
    RecurringExpenseDetails,
)
from shared.repositories.categories import CategoryRecord
from shared.repositories.recurring_expenses import (
    InsertRecurringResult,
    RecurringExpenseRecord,
)

TZ = "America/Sao_Paulo"
NOW = datetime(2026, 8, 31, 14, 20, tzinfo=ZoneInfo(TZ))
SUBSCRIPTIONS_ID = UUID("11111111-1111-1111-1111-111111111111")
HOUSING_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def categories() -> list[CategoryRecord]:
    return [
        CategoryRecord(
            SUBSCRIPTIONS_ID, "Assinaturas", "assinaturas", "Streaming", False
        ),
        CategoryRecord(HOUSING_ID, "Moradia", "moradia", "Casa e contas", False),
    ]


def extracted(**overrides: object) -> ExtractedRecurringExpense:
    payload: dict[str, object] = {
        "description": "Netflix",
        "amount_raw": "55",
        "recurrence_day_hint": "todo dia 10",
        "starts_at_hint": None,
        "payment_method_hint": None,
        "category_hint": "Assinaturas",
        "confidence": 0.95,
    }
    payload.update(overrides)
    return ExtractedRecurringExpense(**payload)


def state(**overrides: object) -> GraphState:
    payload: dict[str, object] = {
        "messages": [HumanMessage(content="minha Netflix é 55 todo dia 10")],
        "phone_number": "5535999228811",
        "channel": "telegram",
        "message_id": "mensagem-original",
        "user_id": str(uuid4()),
        "user_name": None,
        "user_timezone": TZ,
    }
    payload.update(overrides)
    return payload  # type: ignore[return-value]


def _as_record(details: RecurringExpenseDetails) -> RecurringExpenseRecord:
    return RecurringExpenseRecord(
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


@pytest.fixture
def stub_node(monkeypatch: pytest.MonkeyPatch, categories: list[CategoryRecord]):
    """Isola o nó: categorias, relógio, LLM e persistência viram dublês."""
    captured: dict[str, object] = {}

    async def fake_categories(_: str) -> list[CategoryRecord]:
        return categories

    async def fake_insert(
        user_id: str, recurring_expenses: list, source_message_id: str | None = None
    ) -> InsertRecurringResult:
        del user_id
        captured["source_message_id"] = source_message_id
        captured["persisted"] = recurring_expenses
        return InsertRecurringResult(
            inserted=[_as_record(details) for details in recurring_expenses],
            duplicates=[],
        )

    monkeypatch.setattr(add_module, "list_available_categories", fake_categories)
    monkeypatch.setattr(add_module, "insert_recurring_expenses", fake_insert)
    monkeypatch.setattr(add_module.tools_calendar, "user_now", lambda _: NOW)

    def set_extraction(result: AddRecurringExpensesResult) -> None:
        async def fake_extract(*_: object) -> AddRecurringExpensesResult:
            return result

        monkeypatch.setattr(add_module, "_extract", fake_extract)

    captured["set_extraction"] = set_extraction
    captured["monkeypatch"] = monkeypatch
    return captured


def _set(stub_node, **kwargs) -> None:
    stub_node["set_extraction"](AddRecurringExpensesResult(**kwargs))


# ---- TC-001 / TC-002 / TC-003 ----
async def test_one_complete_rule_is_persisted(stub_node):  # TC-001
    _set(stub_node, recurring_expenses=[extracted()])

    result = await add_recurring_expenses(state())

    persisted = stub_node["persisted"]
    assert len(persisted) == 1
    assert persisted[0].description == "Netflix"
    assert persisted[0].amount == Decimal("55.00")
    assert isinstance(persisted[0].amount, Decimal)
    assert persisted[0].recurrence_day == 10
    assert persisted[0].starts_at == date(2026, 8, 31)
    assert persisted[0].category_id == SUBSCRIPTIONS_ID
    assert result["pending_recurring_expenses"] == []
    assert "mensal" in (result["response_text"] or "")


async def test_multiple_rules_in_one_message_are_all_persisted(stub_node):  # TC-002
    _set(
        stub_node,
        recurring_expenses=[
            extracted(
                description="internet", amount_raw="120", recurrence_day_hint="5"
            ),
            extracted(
                description="academia", amount_raw="90", recurrence_day_hint="15"
            ),
        ],
    )

    await add_recurring_expenses(state())

    persisted = stub_node["persisted"]
    assert [rule.description for rule in persisted] == ["internet", "academia"]
    assert [rule.recurrence_day for rule in persisted] == [5, 15]


async def test_complete_rule_survives_an_incomplete_sibling(stub_node):  # TC-003
    _set(
        stub_node,
        recurring_expenses=[
            extracted(),
            extracted(description="academia", recurrence_day_hint=None),
        ],
    )

    result = await add_recurring_expenses(state())

    assert [rule.description for rule in stub_node["persisted"]] == ["Netflix"]
    assert len(result["pending_recurring_expenses"]) == 1
    assert result["pending_recurring_expenses"][0].missing_fields == ["recurrence_day"]


# ---- TC-004 / TC-005 / TC-006 ----
async def test_missing_recurrence_day_becomes_a_pending_draft(stub_node):  # TC-004
    _set(stub_node, recurring_expenses=[extracted(recurrence_day_hint=None)])

    result = await add_recurring_expenses(state())

    assert "persisted" not in stub_node
    pending = result["pending_recurring_expenses"]
    assert len(pending) == 1
    assert pending[0].missing_fields == ["recurrence_day"]
    assert pending[0].id and pending[0].created_at == NOW
    assert "dia do mês" in (result["response_text"] or "")


async def test_unresolvable_category_becomes_a_pending_draft(stub_node):  # TC-005
    """Nunca uma categoria genérica: o relatório é o produto (CON-014)."""
    _set(
        stub_node,
        recurring_expenses=[
            extracted(
                description="mensalidade do clube",
                amount_raw="200",
                recurrence_day_hint="dia 20",
                category_hint=None,
            )
        ],
    )

    result = await add_recurring_expenses(state())

    assert "persisted" not in stub_node
    assert result["pending_recurring_expenses"][0].missing_fields == ["category"]


async def test_missing_description_also_marks_category_as_missing(stub_node):  # TC-006
    _set(
        stub_node,
        pending_recurring_expenses=[
            PendingRecurringExpense(
                amount_raw="200",
                recurrence_day_hint="dia 20",
                category_hint="Moradia",
                missing_fields=["description"],
                clarification_message="Qual gasto fixo de R$200 é esse?",
            )
        ],
    )

    result = await add_recurring_expenses(state())

    pending = result["pending_recurring_expenses"][0]
    assert set(pending.missing_fields) == {"description", "category"}
    assert pending.category_hint is None


# ---- TC-017 ----
async def test_absent_payment_method_resolves_to_not_informed(stub_node):  # TC-017
    _set(stub_node, recurring_expenses=[extracted(payment_method_hint=None)])

    await add_recurring_expenses(state())

    assert stub_node["persisted"][0].payment_method == "not_informed"


async def test_future_start_date_is_accepted(stub_node):  # TC-015 no nó
    _set(stub_node, recurring_expenses=[extracted(starts_at_hint="2026-10-01")])

    await add_recurring_expenses(state())

    assert stub_node["persisted"][0].starts_at == date(2026, 10, 1)


async def test_duplicate_reports_the_existing_rule_and_persists_nothing(
    stub_node, monkeypatch: pytest.MonkeyPatch
):
    existing = RecurringExpenseRecord(
        id=uuid4(),
        description="Netflix",
        amount=Decimal("55.00"),
        payment_method="not_informed",
        recurrence_day=10,
        starts_at=date(2026, 1, 1),
        ends_at=None,
        category_id=SUBSCRIPTIONS_ID,
        category_name="Assinaturas",
    )

    async def fake_insert(**_: object) -> InsertRecurringResult:
        return InsertRecurringResult(inserted=[], duplicates=[existing])

    monkeypatch.setattr(add_module, "insert_recurring_expenses", fake_insert)
    _set(stub_node, recurring_expenses=[extracted(amount_raw="62")])

    result = await add_recurring_expenses(state())

    response = result["response_text"] or ""
    assert "já tem Netflix" in response
    assert "R$ 55.00" in response
    assert "todo dia 10" in response


# ---- TC-020 e demais fronteiras de I/O ----
async def test_category_load_failure_does_not_crash_the_node(  # AC-015
    stub_node, monkeypatch: pytest.MonkeyPatch
):
    async def exploding_categories(_: str) -> list[CategoryRecord]:
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(add_module, "list_available_categories", exploding_categories)
    _set(stub_node, recurring_expenses=[extracted()])

    result = await add_recurring_expenses(state())

    assert result["recurring_expense_details"] == []
    assert result["response_text"]


async def test_insert_failure_does_not_crash_the_node(  # TC-020
    stub_node, monkeypatch: pytest.MonkeyPatch
):
    async def exploding_insert(**_: object) -> InsertRecurringResult:
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(add_module, "insert_recurring_expenses", exploding_insert)
    _set(stub_node, recurring_expenses=[extracted()])

    result = await add_recurring_expenses(state())

    assert "não consegui salvar" in (result["response_text"] or "").lower()


async def test_message_without_a_fixed_expense_asks_for_one(stub_node):
    _set(stub_node)

    result = await add_recurring_expenses(state())

    assert "gasto fixo" in (result["response_text"] or "")


async def test_clarification_without_drafts_keeps_existing_pending(stub_node):
    existing = PendingRecurringExpense(
        id="spotify-pendente",
        description="Spotify",
        amount_raw="21,90",
        missing_fields=["recurrence_day"],
        clarification_message="Em que dia do mês a cobrança do Spotify acontece?",
        created_at=NOW,
    )
    _set(
        stub_node,
        needs_clarification=True,
        clarification_message="Gasto parcelado é registrado como gasto comum.",
    )

    result = await add_recurring_expenses(state(pending_recurring_expenses=[existing]))

    assert result["pending_recurring_expenses"] == [existing]
    assert result["recurring_expense_details"] == []


# ---- Resolução determinística isolada ----
def test_invalid_amount_becomes_a_pending_draft(categories):
    outcome = resolve_extracted_recurring_expenses(
        extracted=[extracted(amount_raw="de graça")],
        categories=categories,
        reference=NOW,
    )

    assert outcome.recurring_expenses == []
    assert outcome.pending_recurring_expenses[0].missing_fields == ["amount"]


def test_blank_description_becomes_a_pending_draft(categories):
    outcome = resolve_extracted_recurring_expenses(
        extracted=[extracted(description="   ")],
        categories=categories,
        reference=NOW,
    )

    assert outcome.pending_recurring_expenses[0].missing_fields == ["description"]


def test_unreadable_start_hint_falls_back_to_today_without_pending(categories):
    outcome = resolve_extracted_recurring_expenses(
        extracted=[extracted(starts_at_hint="qualquer coisa")],
        categories=categories,
        reference=NOW,
    )

    assert outcome.pending_recurring_expenses == []
    assert outcome.recurring_expenses[0].starts_at == date(2026, 8, 31)


def test_confirmation_never_promises_generated_charges():  # GUD-002 / REQ-033
    records = [
        _as_record(
            RecurringExpenseDetails(
                description="Netflix",
                original_description="Netflix",
                amount=Decimal("55.00"),
                category_id=SUBSCRIPTIONS_ID,
                category_name="Assinaturas",
                payment_method="not_informed",
                recurrence_day=10,
                starts_at=date(2026, 8, 31),
            )
        )
    ]

    message = format_recurring_confirmation(records)

    assert "gasto fixo mensal" in message
    assert "Netflix" in message and "55.00" in message
    assert "todo dia 10" in message and "Assinaturas" in message
    assert "lançamento" not in message.lower()


def _rule(description: str, amount: str, day: int) -> RecurringExpenseRecord:
    return _as_record(
        RecurringExpenseDetails(
            description=description,
            original_description=description,
            amount=Decimal(amount),
            category_id=SUBSCRIPTIONS_ID,
            category_name="Assinaturas",
            payment_method="not_informed",
            recurrence_day=day,
            starts_at=date(2026, 8, 31),
        )
    )


def test_confirmation_lists_every_rule_when_there_is_more_than_one():
    message = format_recurring_confirmation(
        [_rule("internet", "120.00", 5), _rule("academia", "90.00", 15)]
    )

    assert "gastos fixos mensais" in message
    assert "internet" in message and "academia" in message
    assert "todo dia 5" in message and "todo dia 15" in message


def test_duplicate_message_lists_every_rule_when_there_is_more_than_one():
    message = format_duplicate_message(
        [_rule("Netflix", "55.00", 10), _rule("Spotify", "21.90", 8)]
    )

    assert "já estavam cadastrados" in message
    assert "Netflix" in message and "Spotify" in message
