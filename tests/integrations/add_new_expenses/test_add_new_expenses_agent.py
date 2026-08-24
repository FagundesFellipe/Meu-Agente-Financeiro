"""Testes do nó de registro de gastos, com LLM e repositórios substituídos.

Nenhum teste aqui toca a rede ou o banco: o objetivo é fixar o comportamento
determinístico que envolve a extração do modelo — o que é salvo, o que vira
pergunta ao usuário e o que nunca é inventado.
"""

from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from financial_agent.agent.ReAct import add_new_expenses_agent as module
from financial_agent.agent.ReAct.add_new_expenses_agent import (
    add_new_expenses,
    build_context_message,
    format_confirmation,
    resolve_extracted_expenses,
)
from financial_agent.agent.state_graph import (
    AddExpensesResult,
    ExtractedExpense,
    GraphState,
    PendingExpense,
)
from shared.repositories.categories import CategoryRecord
from shared.repositories.expenses import ExpenseRecord
from shared.repositories.users import UserRecord

TZ = "America/Sao_Paulo"
NOW = datetime(2026, 8, 3, 14, 20, tzinfo=ZoneInfo(TZ))

FOOD_ID = UUID("11111111-1111-1111-1111-111111111111")
TRANSPORT_ID = UUID("22222222-2222-2222-2222-222222222222")
OTHER_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def categories():
    return [
        CategoryRecord(FOOD_ID, "Alimentação", "alimentacao", "Restaurantes", False),
        CategoryRecord(TRANSPORT_ID, "Transporte", "transporte", "Combustível", False),
        CategoryRecord(OTHER_ID, "Outros gastos", "outros_gastos", "Diversos", False),
    ]


@pytest.fixture
def user():
    return UserRecord(
        id=uuid4(),
        channel="telegram",
        external_user_id="5535999228811",
        name="Fellipe",
        timezone=TZ,
        currency="BRL",
        onboarding_status="done",
    )


def extracted(**overrides) -> ExtractedExpense:
    payload = {
        "description": "almoço",
        "amount_raw": "35",
        "installments": None,
        "date_hint": None,
        "time_hint": None,
        "payment_method_hint": None,
        "category_hint": "Alimentação",
        "confidence": 0.95,
    }
    payload.update(overrides)
    return ExtractedExpense(**payload)


# --------------------------------------------------------------------------
# Pós-processamento determinístico
# --------------------------------------------------------------------------


def test_resolves_a_simple_expense(categories):
    outcome = resolve_extracted_expenses([extracted()], categories, TZ, NOW)

    assert outcome.problems == []
    assert len(outcome.expenses) == 1

    expense = outcome.expenses[0]
    assert expense.amount == Decimal("35.00")
    assert isinstance(expense.amount, Decimal)
    assert expense.category_id == FOOD_ID
    assert expense.payment_method == "not_informed"
    assert expense.occurred_at.date() == NOW.date()


def test_resolves_multiple_expenses_from_one_message(categories):
    outcome = resolve_extracted_expenses(
        [
            extracted(),
            extracted(
                description="gasolina",
                amount_raw="50",
                category_hint="Transporte",
                payment_method_hint="credit_card",
            ),
        ],
        categories,
        TZ,
        NOW,
    )

    assert [e.category_id for e in outcome.expenses] == [FOOD_ID, TRANSPORT_ID]
    assert outcome.expenses[1].amount == Decimal("50.00")
    assert outcome.expenses[1].payment_method == "credit_card"


def test_unparseable_amount_becomes_a_question_not_a_saved_expense(categories):
    outcome = resolve_extracted_expenses(
        [extracted(amount_raw="uns cinquenta e pouco")], categories, TZ, NOW
    )

    assert outcome.expenses == []
    assert len(outcome.problems) == 1
    assert "valor" in outcome.problems[0].lower()


def test_future_date_becomes_a_question(categories):
    outcome = resolve_extracted_expenses(
        [extracted(date_hint="2026-09-01")], categories, TZ, NOW
    )

    assert outcome.expenses == []
    assert "data" in outcome.problems[0].lower()


def test_clear_expense_is_kept_even_when_a_sibling_is_ambiguous(categories):
    """Regra do PRD: itens inequívocos da mesma mensagem continuam sendo salvos."""
    outcome = resolve_extracted_expenses(
        [
            extracted(),
            extracted(description="posto", amount_raw="um tanto"),
        ],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 1
    assert outcome.expenses[0].description == "almoço"
    assert len(outcome.problems) == 1
    assert "valor" in outcome.problems[0].lower()


def test_hallucinated_category_never_reaches_persistence(categories):
    outcome = resolve_extracted_expenses(
        [extracted(category_hint="Categoria Inventada")], categories, TZ, NOW
    )

    assert outcome.expenses[0].category_id in {FOOD_ID, TRANSPORT_ID, OTHER_ID}


def test_original_description_is_preserved_for_audit(categories):
    outcome = resolve_extracted_expenses(
        [extracted(description="  ração do cachorro  ")], categories, TZ, NOW
    )

    assert outcome.expenses[0].original_description == "ração do cachorro"


# --------------------------------------------------------------------------
# Parcelamento
# --------------------------------------------------------------------------


def test_installment_expense_expands_into_n_records(categories):
    outcome = resolve_extracted_expenses(
        [extracted(description="sapato", amount_raw="50", installments=3)],
        categories,
        TZ,
        NOW,
    )

    assert outcome.problems == []
    assert len(outcome.expenses) == 3
    assert all(e.amount == Decimal("50.00") for e in outcome.expenses)
    assert all(e.total_installments == 3 for e in outcome.expenses)
    assert [e.installment_number for e in outcome.expenses] == [1, 2, 3]


def test_installment_descriptions_include_parcel_marker(categories):
    outcome = resolve_extracted_expenses(
        [extracted(description="sapato", amount_raw="50", installments=3)],
        categories,
        TZ,
        NOW,
    )

    assert outcome.expenses[0].description == "sapato (1/3)"
    assert outcome.expenses[1].description == "sapato (2/3)"
    assert outcome.expenses[2].description == "sapato (3/3)"


def test_installment_dates_are_monthly_apart(categories):
    outcome = resolve_extracted_expenses(
        [extracted(description="sapato", amount_raw="50", installments=3)],
        categories,
        TZ,
        NOW,
    )

    dates = [e.occurred_at.date() for e in outcome.expenses]
    assert dates == [
        datetime(2026, 8, 3).date(),
        datetime(2026, 9, 3).date(),
        datetime(2026, 10, 3).date(),
    ]


def test_installment_original_description_is_not_suffixed(categories):
    outcome = resolve_extracted_expenses(
        [extracted(description="sapato", amount_raw="50", installments=2)],
        categories,
        TZ,
        NOW,
    )

    assert all(e.original_description == "sapato" for e in outcome.expenses)


def test_installments_none_produces_single_expense(categories):
    outcome = resolve_extracted_expenses(
        [extracted(installments=None)],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 1
    assert outcome.expenses[0].installment_number is None
    assert outcome.expenses[0].total_installments is None


def test_installments_one_produces_single_expense(categories):
    outcome = resolve_extracted_expenses(
        [extracted(installments=1)],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 1
    assert outcome.expenses[0].installment_number is None
    assert outcome.expenses[0].total_installments is None


def test_add_months_clamps_day_at_end_of_month():
    from financial_agent.agent.ReAct.add_new_expenses_agent import _add_months

    jan_31 = datetime(2026, 1, 31, 10, 0, tzinfo=ZoneInfo(TZ))
    feb = _add_months(jan_31, 1)
    assert feb.date() == datetime(2026, 2, 28).date()


# --------------------------------------------------------------------------
# amount_is_total
# --------------------------------------------------------------------------


def test_amount_is_total_divides_total_by_installments(categories):
    """'de 300 em 5x' → 5 parcelas de 60."""
    outcome = resolve_extracted_expenses(
        [
            extracted(
                description="sapato",
                amount_raw="300",
                installments=5,
                amount_is_total=True,
            )
        ],
        categories,
        TZ,
        NOW,
    )

    assert outcome.problems == []
    assert len(outcome.expenses) == 5
    assert all(e.amount == Decimal("60.00") for e in outcome.expenses)
    assert all(e.total_installments == 5 for e in outcome.expenses)
    assert [e.installment_number for e in outcome.expenses] == [1, 2, 3, 4, 5]


def test_amount_is_total_false_does_not_divide(categories):
    """amount_is_total=false (default): valor já é da parcela, não divide."""
    outcome = resolve_extracted_expenses(
        [extracted(description="sapato", amount_raw="50", installments=3)],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 3
    assert all(e.amount == Decimal("50.00") for e in outcome.expenses)


def test_amount_is_total_without_installments_is_ignored(categories):
    """amount_is_total=true sem installments ou com installments=1 → sem divisão."""
    outcome = resolve_extracted_expenses(
        [
            extracted(
                description="almoço",
                amount_raw="35",
                installments=None,
                amount_is_total=True,
            )
        ],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 1
    assert outcome.expenses[0].amount == Decimal("35.00")


def test_amount_is_total_with_one_installment_is_ignored(categories):
    """amount_is_total=true com installments=1 → sem divisão."""
    outcome = resolve_extracted_expenses(
        [
            extracted(
                description="almoço",
                amount_raw="35",
                installments=1,
                amount_is_total=True,
            )
        ],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 1
    assert outcome.expenses[0].amount == Decimal("35.00")


def test_amount_is_total_non_exact_division(categories):
    """100 / 3 = 33,333... → resto de 1 centavo vai para a 1ª parcela."""
    outcome = resolve_extracted_expenses(
        [
            extracted(
                description="item",
                amount_raw="100",
                installments=3,
                amount_is_total=True,
            )
        ],
        categories,
        TZ,
        NOW,
    )

    assert len(outcome.expenses) == 3
    amounts = [e.amount for e in outcome.expenses]
    assert amounts == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(amounts) == Decimal("100.00")


def test_amount_is_total_division_remainder_never_changes_the_total(categories):
    """5000 / 12 = 416,6666... → soma das parcelas bate exatamente 5000,00."""
    outcome = resolve_extracted_expenses(
        [
            extracted(
                description="cadeira gamer",
                amount_raw="5000",
                installments=12,
                amount_is_total=True,
            )
        ],
        categories,
        TZ,
        NOW,
    )

    amounts = [e.amount for e in outcome.expenses]
    assert sum(amounts) == Decimal("5000.00")
    assert amounts[0] == Decimal("416.67")
    assert amounts[-1] == Decimal("416.66")


# --------------------------------------------------------------------------
# Contexto e confirmação
# --------------------------------------------------------------------------


def test_context_message_carries_date_and_all_categories(categories):
    message = build_context_message(NOW, categories)

    assert NOW.isoformat() in message.content
    for category in categories:
        assert category.name in message.content


def test_confirmation_for_a_single_expense():
    record = ExpenseRecord(
        id=uuid4(),
        amount=Decimal("35.00"),
        description="almoço",
        original_description="almoço",
        payment_method="not_informed",
        occurred_at=NOW,
        category_id=FOOD_ID,
        category_name="Alimentação",
    )

    assert format_confirmation([record]) == (
        "Anotado: almoço — R$ 35.00 (Alimentação)."
    )


def test_confirmation_for_multiple_expenses_shows_total():
    records = [
        ExpenseRecord(
            uuid4(),
            Decimal("30.00"),
            "almoço",
            "almoço",
            "not_informed",
            NOW,
            FOOD_ID,
            "Alimentação",
        ),
        ExpenseRecord(
            uuid4(),
            Decimal("50.00"),
            "gasolina",
            "gasolina",
            "credit_card",
            NOW,
            TRANSPORT_ID,
            "Transporte",
        ),
    ]

    text = format_confirmation(records)

    assert "Total: R$ 80.00" in text
    assert "almoço" in text and "gasolina" in text


# --------------------------------------------------------------------------
# Nó completo
# --------------------------------------------------------------------------


@pytest.fixture
def stub_node(monkeypatch, user, categories):
    """Substitui LLM e repositórios; devolve o que foi "persistido"."""
    persisted: dict = {}

    async def fake_categories(user_id):
        return categories

    async def fake_insert(user_id, expenses, source_message_id=None):
        persisted["insert_calls"] = persisted.get("insert_calls", 0) + 1
        persisted["user_id"] = user_id
        persisted["source_message_id"] = source_message_id
        persisted["expenses"] = expenses
        return [
            ExpenseRecord(
                id=uuid4(),
                amount=e.amount,
                description=e.description,
                original_description=e.original_description,
                payment_method=e.payment_method,
                occurred_at=e.occurred_at,
                category_id=e.category_id,
                category_name=e.category_name,
                installment_number=e.installment_number,
                total_installments=e.total_installments,
            )
            for e in expenses
        ]

    monkeypatch.setattr(module, "list_available_categories", fake_categories)
    monkeypatch.setattr(module, "insert_expenses", fake_insert)
    monkeypatch.setattr(module.tools_calendar, "user_now", lambda tz=None: NOW)

    def set_extraction(result: AddExpensesResult):
        async def fake_extract(state, context):
            persisted["context"] = context
            return result

        monkeypatch.setattr(module, "_extract", fake_extract)

    persisted["set_extraction"] = set_extraction
    return persisted


def make_state(**overrides) -> GraphState:
    state: dict = {
        "messages": [{"role": "user", "content": "Gastei 35 reais no almoço"}],
        "phone_number": "5535999228811",
        "channel": "telegram",
        "message_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "user_id": str(uuid4()),
        "user_name": None,
        "user_timezone": TZ,
    }
    state.update(overrides)
    return cast(GraphState, state)


async def test_node_persists_and_confirms(stub_node):
    stub_node["set_extraction"](AddExpensesResult(expenses=[extracted()]))

    result = await add_new_expenses(make_state())

    assert stub_node["insert_calls"] == 1
    assert stub_node["expenses"][0].amount == Decimal("35.00")
    assert "Anotado" in result["response_text"]
    assert len(result["expense_details"]) == 1


async def test_node_forwards_message_id_for_idempotency(stub_node):
    stub_node["set_extraction"](AddExpensesResult(expenses=[extracted()]))

    await add_new_expenses(make_state())

    assert stub_node["source_message_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


async def test_node_asks_instead_of_saving_when_model_flags_ambiguity(stub_node):
    stub_node["set_extraction"](
        AddExpensesResult(
            expenses=[],
            needs_clarification=True,
            clarification_message="Qual foi o valor exato?",
        )
    )

    result = await add_new_expenses(make_state())

    assert "insert_calls" not in stub_node
    assert "não consegui identificar" in result["response_text"].lower()


async def test_node_combines_confirmation_and_pending_question(stub_node):
    stub_node["set_extraction"](
        AddExpensesResult(
            expenses=[extracted(source_start=0, source_end=9, source_text="almoço 35")],
            needs_clarification=True,
            pending_expenses=[
                PendingExpense(
                    source_start=10,
                    source_end=18,
                    source_text="posto 20",
                    description="posto",
                    missing_fields=["amount"],
                    clarification_message="Quanto você gastou no posto?",
                )
            ],
        )
    )

    result = await add_new_expenses(
        make_state(messages=[{"role": "user", "content": "almoço 35 posto 20"}])
    )

    assert "Anotado" in result["response_text"]
    assert "Quanto você gastou no posto?" in result["response_text"]


async def test_node_handles_empty_extraction(stub_node):
    stub_node["set_extraction"](AddExpensesResult(expenses=[]))

    result = await add_new_expenses(make_state())

    assert "insert_calls" not in stub_node
    assert "não consegui identificar" in result["response_text"].lower()


async def test_node_injects_user_categories_into_the_llm_context(stub_node, categories):
    stub_node["set_extraction"](AddExpensesResult(expenses=[extracted()]))

    await add_new_expenses(make_state())

    context = stub_node["context"].content
    for category in categories:
        assert category.name in context
