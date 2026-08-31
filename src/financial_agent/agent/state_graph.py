"""Esquema do grafo de estado e definições de tipo do agente financeiro.

Este módulo define os contratos de dados centrais usados em todo o agente LangGraph:
estado do grafo (TypedDict), payloads de gastos e gastos recorrentes (Pydantic),
e aliases de tipo literal para categorias e intenções.

Divisão de responsabilidades:
    - ``ExtractedExpense`` é o que o LLM devolve (texto cru, ainda não validado).
    - ``ExpenseDetails`` é o resultado determinístico do pós-processamento em
      Python (valor em ``Decimal``, data resolvida, categoria existente no banco),
      pronto para persistência.

A mesma divisão vale para gasto recorrente (``ExtractedRecurringExpense`` ->
``RecurringExpenseDetails``). Os dois fluxos usam listas fisicamente separadas
no estado: um rascunho de gasto fixo nunca pode chegar ao resolvedor de gasto
pontual, e vice-versa.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, NotRequired
from uuid import UUID

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import TypedDict

Intentions = Literal[
    "add_new_expenses",
    "continue_pending_expense",
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

    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)
    source_text: str | None = Field(
        default=None,
        description="Trecho literal da mensagem entre source_start e source_end",
    )
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


PendingExpenseField = Literal[
    "description",
    "amount",
    "installments",
    "date",
    "category",
    "payment_method",
]

PendingExpenseResolutionRoute = Literal[
    "add_new_expenses_agent",
    "finalize_response",
]


class PendingExpense(BaseModel):
    """Rascunho de gasto que ainda não está autorizado a ser persistido.

    O identificador e a data de criação são atribuídos pelo servidor. Os demais
    campos preservam apenas o que já foi extraído, para que uma continuação não
    precise reenviar o histórico inteiro ao modelo.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(
        default=None, description="Identificador estável do rascunho"
    )
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)
    source_text: str | None = Field(
        default=None,
        description="Trecho literal da mensagem entre source_start e source_end",
    )
    description: str | None = None
    amount_raw: str | None = None
    installments: int | None = Field(default=None, ge=1)
    amount_is_total: bool = False
    date_hint: str | None = None
    time_hint: str | None = None
    payment_method_hint: PaymentMethodHint | None = None
    category_hint: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_fields: list[PendingExpenseField] = Field(min_length=1)
    clarification_message: str = Field(min_length=1)
    created_at: datetime | None = None


class AddExpensesResult(BaseModel):
    """Resposta estruturada do sub-agente de registro de gastos."""

    model_config = ConfigDict(extra="forbid")

    expenses: list[ExtractedExpense] = Field(
        default_factory=list,
        description="Gastos completos e autorizados a seguir para validação",
    )
    pending_expenses: list[PendingExpense] = Field(
        default_factory=list,
        description="Rascunhos incompletos que nunca podem entrar em expenses",
    )
    needs_clarification: bool = Field(
        default=False, description="True quando falta informação para registrar"
    )
    clarification_message: str | None = Field(
        default=None, description="Pergunta a enviar ao usuário quando há ambiguidade"
    )

    @model_validator(mode="after")
    def synchronize_clarification_flag(self) -> "AddExpensesResult":
        """Mantém o campo legado coerente quando há rascunhos estruturados."""
        if self.pending_expenses:
            self.needs_clarification = True
        return self


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


# ---- GASTO RECORRENTE (regra mensal, tabela ``recurring_expense``) ----
class ExtractedRecurringExpense(BaseModel):
    """Regra de gasto fixo bruta, extraída pelo LLM antes de qualquer validação.

    Como em ``ExtractedExpense``, todos os campos são "hints": o modelo apenas
    transcreve o que o usuário disse. Não existe ``installments`` aqui —
    parcelamento é conceito de gasto pontual, não de regra mensal.
    """

    model_config = ConfigDict(extra="forbid")

    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)
    source_text: str | None = Field(
        default=None,
        description="Trecho literal da mensagem entre source_start e source_end",
    )
    description: str = Field(
        description="Rótulo do gasto fixo, sem o valor. Ex.: 'Netflix', 'academia'"
    )
    amount_raw: str = Field(
        description=(
            "Valor mensal usando apenas algarismos (0-9), vírgula como separador "
            "decimal. Converta texto por extenso para dígitos ('cinquenta reais' "
            "vira '50'). Remova símbolos de moeda (R$). Ex.: '55', '21,90'."
        )
    )
    recurrence_day_hint: str | None = Field(
        default=None,
        description=(
            "Dia do mês em que a cobrança acontece, como texto. "
            "Ex.: '10', 'todo dia 5'. null quando o usuário não informou."
        ),
    )
    starts_at_hint: str | None = Field(
        default=None,
        description="Data de início da recorrência em YYYY-MM-DD, ou null",
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
        ge=0.0, le=1.0, description="Confiança do modelo na extração desta regra"
    )


PendingRecurringExpenseField = Literal[
    "description",
    "amount",
    "recurrence_day",
    "category",
]

PendingRecurringExpenseResolutionRoute = Literal[
    "add_recurring_expenses_agent",
    "finalize_response",
]


class PendingRecurringExpense(BaseModel):
    """Rascunho de regra mensal que ainda não pode ser persistida.

    Espelha ``ExtractedRecurringExpense`` com todos os campos opcionais. O
    identificador e a data de criação são atribuídos pelo servidor; esta última
    marca o início da janela de 24 horas do TTL.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(
        default=None, description="Identificador estável do rascunho"
    )
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)
    source_text: str | None = Field(
        default=None,
        description="Trecho literal da mensagem entre source_start e source_end",
    )
    description: str | None = None
    amount_raw: str | None = None
    recurrence_day_hint: str | None = None
    starts_at_hint: str | None = None
    payment_method_hint: PaymentMethodHint | None = None
    category_hint: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_fields: list[PendingRecurringExpenseField] = Field(min_length=1)
    clarification_message: str = Field(min_length=1)
    created_at: datetime | None = None


class AddRecurringExpensesResult(BaseModel):
    """Resposta estruturada do sub-agente de cadastro de gastos fixos."""

    model_config = ConfigDict(extra="forbid")

    recurring_expenses: list[ExtractedRecurringExpense] = Field(
        default_factory=list,
        description="Regras completas e autorizadas a seguir para validação",
    )
    pending_recurring_expenses: list[PendingRecurringExpense] = Field(
        default_factory=list,
        description="Rascunhos incompletos que nunca podem entrar em "
        "recurring_expenses",
    )
    needs_clarification: bool = Field(
        default=False, description="True quando falta informação para cadastrar"
    )
    clarification_message: str | None = Field(
        default=None, description="Pergunta a enviar ao usuário quando há ambiguidade"
    )

    @model_validator(mode="after")
    def synchronize_clarification_flag(self) -> "AddRecurringExpensesResult":
        """Mantém o campo legado coerente quando há rascunhos estruturados."""
        if self.pending_recurring_expenses:
            self.needs_clarification = True
        return self


class RecurringExpenseDetails(BaseModel):
    """Regra já validada em Python, pronta para a tabela ``recurring_expense``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(description="Descrição normalizada da regra")
    original_description: str = Field(
        description="Texto original do usuário, preservado para auditoria"
    )
    amount: Decimal = Field(
        description="Valor mensal decimal exato (nunca float binário)"
    )
    category_id: UUID = Field(description="Categoria existente no banco")
    category_name: str = Field(description="Nome da categoria, para a confirmação")
    payment_method: PaymentMethod = Field(description="Meio de pagamento canônico")
    recurrence_day: int = Field(
        ge=1, le=31, description="Dia do mês da cobrança, gravado sem clamp"
    )
    starts_at: date = Field(
        description="Primeiro mês em que a regra vale. Pode estar no futuro."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confiança da extração pelo LLM"
    )


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
    pending_expenses: NotRequired[list[PendingExpense]]
    expired_pending_expenses: NotRequired[list[PendingExpense]]
    pending_expense_resolution_route: NotRequired[PendingExpenseResolutionRoute]
    needs_clarification: NotRequired[bool]
    clarification_message: NotRequired[str | None]
    expense_details: NotRequired[list[ExpenseDetails]]
    pending_recurring_expenses: NotRequired[list[PendingRecurringExpense]]
    expired_pending_recurring_expenses: NotRequired[list[PendingRecurringExpense]]
    pending_recurring_expense_resolution_route: NotRequired[
        PendingRecurringExpenseResolutionRoute
    ]
    recurring_expense_details: NotRequired[list[RecurringExpenseDetails]]
    response_text: NotRequired[str | None]
    errors: NotRequired[list[str]]
