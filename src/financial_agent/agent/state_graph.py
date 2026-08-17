"""Esquema do grafo de estado e definições de tipo do agente financeiro.

Este módulo define os contratos de dados centrais usados em todo o agente LangGraph:
estado do grafo (TypedDict), payloads de gastos e gastos recorrentes (Pydantic),
e aliases de tipo literal para categorias e intenções.

Divisão de responsabilidades:
    - ``ExtractedExpense`` é o que o LLM devolve (texto cru, ainda não validado).
    - ``ExpenseDetails`` é o resultado determinístico do pós-processamento em
      Python (valor em ``Decimal``, data resolvida, categoria existente no banco),
      pronto para persistência.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, NotRequired
from uuid import UUID

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

Intentions = Literal[
    "add_new_expenses",
    "add_categories_recurring_expenses",
    "view_expenses_report",
    "greeting",
    "undefined",
]

PaymentMethod = Literal[
    "pix",
    "credit_card",
    "debit_card",
    "cash",
    "not_informed",
]

# Subconjunto que o LLM pode sugerir: "not_informed" é decidido em Python,
# nunca inferido pelo modelo.
PaymentMethodHint = Literal["pix", "credit_card", "debit_card", "cash"]


class ExtractedExpense(BaseModel):
    """Gasto bruto extraído pelo LLM, antes de qualquer validação determinística.

    Todos os campos são "hints": o LLM apenas transcreve o que o usuário disse.
    A conversão para ``Decimal``/``datetime``/``category_id`` acontece em Python.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        description="O que foi comprado ou pago, nas palavras do usuário, sem o valor"
    )
    amount_raw: str = Field(
        description=(
            "Valor usando apenas algarismos (0-9), vírgula como separador decimal. "
            "Converta texto por extenso para dígitos ('duzentos reais' vira '200'). "
            "Remova símbolos de moeda (R$). Em parcelamentos, informe o valor de "
            "CADA parcela, não o total. Ex: '35', '120,50', '8,50', '12.90'."
        )
    )
    installments: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Número de parcelas. null ou 1 = pagamento à vista/único. "
            ">1 = gasto parcelado. Ex: 3 para '3x de 50'."
        ),
    )
    amount_is_total: bool = Field(
        default=False,
        description=(
            "true = o valor em amount_raw é o TOTAL da compra parcelada "
            "(o Python fará a divisão). false = amount_raw já é o valor de "
            "cada parcela. Ex: 'de 300 em 5x' → true; '3x de 50' → false."
        ),
    )
    date_hint: str | None = Field(
        default=None,
        description="Data do gasto em YYYY-MM-DD, ou null se o usuário não informou",
    )
    time_hint: str | None = Field(
        default=None,
        description="Horário em HH:MM, ou null se o usuário não informou",
    )
    payment_method_hint: PaymentMethodHint | None = Field(
        default=None,
        description="Meio de pagamento canônico, ou null se o usuário não informou",
    )
    category_hint: str | None = Field(
        default=None,
        description="Nome exato de uma categoria disponível, ou null",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confiança do modelo na extração deste gasto"
    )


class AddExpensesResult(BaseModel):
    """Resposta estruturada do sub-agente de registro de gastos."""

    model_config = ConfigDict(extra="forbid")

    expenses: list[ExtractedExpense] = Field(
        default_factory=list, description="Gastos aproveitáveis extraídos da mensagem"
    )
    needs_clarification: bool = Field(
        default=False, description="True quando falta informação para registrar"
    )
    clarification_message: str | None = Field(
        default=None, description="Pergunta a enviar ao usuário quando há ambiguidade"
    )


class ExpenseDetails(BaseModel):
    """Gasto já validado em Python e pronto para ser gravado na tabela ``expense``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(description="Descrição normalizada do gasto")
    original_description: str = Field(
        description="Texto original do usuário, preservado para auditoria"
    )
    amount: Decimal = Field(description="Valor decimal exato (nunca float binário)")
    occurred_at: datetime = Field(
        description="Momento do gasto, com timezone do usuário aplicado"
    )
    category_id: UUID = Field(description="Categoria existente no banco")
    category_name: str = Field(description="Nome da categoria, para a confirmação")
    payment_method: PaymentMethod = Field(description="Meio de pagamento canônico")
    installment_number: int | None = Field(
        default=None,
        ge=1,
        description="Número desta parcela (1-based). null = gasto à vista.",
    )
    total_installments: int | None = Field(
        default=None,
        ge=1,
        description="Total de parcelas. null = gasto à vista.",
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confiança da extração pelo LLM"
    )


class RecurringExpense(BaseModel):
    """Gasto recorrente identificado pelo agente.

    Indexado por descrição no estado do grafo.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(
        description="Rótulo legível por humanos, por exemplo 'Spotify Premium''"
    )
    category: str = Field(description="Categoria da despesa da lista predefinida")
    amount: str = Field(description="Valor mensal")


class InputState(TypedDict):
    """Campos aceitos na invocação do grafo."""

    messages: Annotated[list[AnyMessage], add_messages]
    phone_number: str
    channel: Literal["telegram", "whatsapp"]
    message_id: NotRequired[str | None]


class GraphState(TypedDict):
    """Estado por usuário transportado através do grafo do agente LangGraph.

    Cada campo tem escopo de uma única sessão de usuário. O redutor do grafo
    (add_messages) adiciona novas mensagens em vez de sobrescrever a lista.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    phone_number: str
    channel: str
    user_id: str
    user_name: str | None
    user_timezone: str
    is_new_user: NotRequired[bool]
    message_id: NotRequired[str | None]
    intention: NotRequired[Intentions]
    extracted_expenses: NotRequired[list[ExtractedExpense]]
    needs_clarification: NotRequired[bool]
    clarification_message: NotRequired[str | None]
    expense_details: NotRequired[list[ExpenseDetails]]
    recurring_monthly_expenses: NotRequired[RecurringExpense | None]
    response_text: NotRequired[str | None]
    errors: NotRequired[list[str]]
