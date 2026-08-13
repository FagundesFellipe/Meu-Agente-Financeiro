from __future__ import annotations

import json
import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from deepeval.metrics import BaseMetric, GEval, JsonCorrectnessMetric
from deepeval.metrics.g_eval import Rubric
from deepeval.models import OpenRouterModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from financial_agent.agent.state_graph import AddExpensesResult, ExtractedExpense


def build_json_correctness_metric() -> JsonCorrectnessMetric:
    """Métrica de schema: garante que o JSON respeita AddExpensesResult."""
    return JsonCorrectnessMetric(
        expected_schema=AddExpensesResult(expenses=[]),
        model=OpenRouterModel(),
        verbose_mode=True,
        async_mode=True,
        strict_mode=True,
    )


class ExpenseExtractionCorrectnessMetric(BaseMetric):
    """Métrica determinística que compara valores do JSON extraído com o esperado.

    Diferente de :class:`JsonCorrectnessMetric`, que só valida schema, esta
    métrica pontua campo a campo (descrição, valor, parcelas, data, categoria,
    meio de pagamento, etc.) e retorna um score contínuo entre 0 e 1.
    """

    _EXPENSE_WEIGHTS = {
        "description": 0.20,
        "amount_raw": 0.25,
        "installments": 0.10,
        "amount_is_total": 0.10,
        "date_hint": 0.10,
        "time_hint": 0.05,
        "payment_method_hint": 0.10,
        "category_hint": 0.10,
    }

    def __init__(
        self,
        threshold: float = 0.7,
        strict_mode: bool = False,
        async_mode: bool = True,
        verbose_mode: bool = True,
        include_reason: bool = True,
    ) -> None:
        self.threshold = 1.0 if strict_mode else threshold
        self._threshold: float = self.threshold
        self.strict_mode = strict_mode
        self.async_mode = async_mode
        self.verbose_mode = verbose_mode
        self.include_reason = include_reason
        self.score: float | None = None
        self.reason: str | None = None
        self.success: bool | None = None
        self.error: str | None = None

    def measure(self, test_case: LLMTestCase, _=None) -> float:
        try:
            actual = self._parse_result(test_case.actual_output)
            expected = self._parse_result(test_case.expected_output)
            self.score = self._score_results(actual, expected)
            self.success = self.score >= self._threshold
            self.reason = self._build_reason(actual, expected)
            return self.score
        except Exception as exc:  # pragma: no cover - deepeval captura erros
            self.error = str(exc)
            self.success = False
            raise

    async def a_measure(self, test_case: LLMTestCase, _=None) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        if self.error is not None:
            self.success = False
        elif self.score is not None:
            self.success = self.score >= self._threshold
        return bool(self.success)

    @property
    def __name__(self) -> str:  # type: ignore[override]
        return "Expense Extraction Correctness"

    @staticmethod
    def _parse_result(raw: str | None) -> AddExpensesResult:
        if raw is None:
            return AddExpensesResult(expenses=[])
        data = json.loads(raw)
        return AddExpensesResult(**data)

    def _score_results(
        self, actual: AddExpensesResult, expected: AddExpensesResult
    ) -> float:
        needs_clarification_match = (
            actual.needs_clarification == expected.needs_clarification
        )

        clarification_score = 1.0
        if expected.needs_clarification and actual.needs_clarification:
            clarification_score = _text_similarity(
                actual.clarification_message or "",
                expected.clarification_message or "",
            )

        expenses_score = self._score_expenses(actual.expenses, expected.expenses)

        # Pesos de topo: precisão da classificação de ambiguidade pesa 20%;
        # quando há ambiguidade, a mensagem pesa 20%; os gastos ocupam o resto.
        if expected.needs_clarification:
            score = (
                0.20 * float(needs_clarification_match)
                + 0.20 * clarification_score
                + 0.60 * expenses_score
            )
        else:
            score = 0.20 * float(needs_clarification_match) + 0.80 * expenses_score

        return round(score, 4)

    def _score_expenses(
        self, actual: list[ExtractedExpense], expected: list[ExtractedExpense]
    ) -> float:
        if not expected and not actual:
            return 1.0
        if not expected or not actual:
            return 0.0

        min_len = min(len(actual), len(expected))
        max_len = max(len(actual), len(expected))

        pair_scores = [
            self._score_expense(actual[i], expected[i]) for i in range(min_len)
        ]
        base_score = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0

        # Penaliza diferença de quantidade de gastos extraídos.
        size_penalty = (max_len - min_len) / max_len
        return round(base_score * (1 - size_penalty), 4)

    def _score_expense(
        self, actual: ExtractedExpense, expected: ExtractedExpense
    ) -> float:
        scores: dict[str, float] = {
            "description": _text_similarity(actual.description, expected.description),
            "amount_raw": _amount_similarity(actual.amount_raw, expected.amount_raw),
            "installments": _exact_similarity(
                actual.installments, expected.installments
            ),
            "amount_is_total": _exact_similarity(
                actual.amount_is_total, expected.amount_is_total
            ),
            "date_hint": _exact_similarity(actual.date_hint, expected.date_hint),
            "time_hint": _exact_similarity(actual.time_hint, expected.time_hint),
            "payment_method_hint": _exact_similarity(
                actual.payment_method_hint, expected.payment_method_hint
            ),
            "category_hint": _text_similarity(
                actual.category_hint or "",
                expected.category_hint or "",
            ),
        }

        return round(
            sum(
                scores[field] * weight
                for field, weight in self._EXPENSE_WEIGHTS.items()
            ),
            4,
        )

    def _build_reason(
        self, actual: AddExpensesResult, expected: AddExpensesResult
    ) -> str:
        if not self.include_reason:
            return ""

        parts = [
            f"needs_clarification: actual={actual.needs_clarification}, "
            f"expected={expected.needs_clarification}",
            f"expenses count: actual={len(actual.expenses)}, "
            f"expected={len(expected.expenses)}",
        ]
        return "; ".join(parts)


def build_value_correctness_metric() -> ExpenseExtractionCorrectnessMetric:
    """Métrica de valores: compara cada campo da extração com o esperado."""
    return ExpenseExtractionCorrectnessMetric(
        threshold=0.75,
        strict_mode=False,
        async_mode=True,
        verbose_mode=True,
        include_reason=True,
    )


def build_correctness_metrics() -> GEval:
    """Métrica baseada em LLM (GEval) para julgamento semântico da resposta."""
    criteria = (
        "Compare cada campo no JSON atual com os valores esperados "
        "e verifique se os valores estão corretos."
    )

    evaluation_steps = [
        "Leia todos os campos e valores esperados",
        (
            "Compare e verifique se há contradições sobre categorias, "
            "números de parcelas, total gasto, dia do gasto"
        ),
        "Verifique se há definições de gastos com informações faltantes",
        (
            "Não penalize pequenas diferenças em descrições que não irão "
            "alterar significativamente o gasto"
        ),
    ]

    rubric = [
        Rubric(
            score_range=(0, 2),
            expected_outcome=(
                "Resposta incorreta, campos obrigatórios faltando, "
                "definição totalmente aleatória de categorias e datas."
            ),
        ),
        Rubric(
            score_range=(3, 5),
            expected_outcome=(
                "Resposta parcialmente correta, mas com omissões importantes "
                "que afetam o registro"
            ),
        ),
        Rubric(
            score_range=(6, 8),
            expected_outcome=(
                "Resposta majoritariamente correta, com pequenas perdas "
                "de detalhes ou clareza."
            ),
        ),
        Rubric(
            score_range=(9, 10),
            expected_outcome="Resposta correta, completa e compatível com o esperado",
        ),
    ]

    return GEval(
        name="Field Correctness",
        criteria=criteria,
        evaluation_steps=evaluation_steps,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        rubric=rubric,
        threshold=0.7,
        model=OpenRouterModel(),
        async_mode=True,
        verbose_mode=True,
    )


# ---------------------------------------------------------------------------
# Helpers de comparação
# ---------------------------------------------------------------------------


def _normalize_text(value: str) -> str:
    """Lowercase, sem acentos e sem espaços extras."""
    value = value.strip().lower()
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(value.split())


def _text_similarity(actual: str, expected: str) -> float:
    """Similaridade entre textos, tolerante a capitalização e acentos."""
    if _normalize_text(actual) == _normalize_text(expected):
        return 1.0
    return round(SequenceMatcher(None, actual.lower(), expected.lower()).ratio(), 4)


def _exact_similarity(actual, expected) -> float:
    """Comparação exata, tratando None como igual a None."""
    return 1.0 if actual == expected else 0.0


def _amount_similarity(actual: str, expected: str) -> float:
    """Compara valores monetários normalizando separadores decimais."""
    try:
        return 1.0 if _parse_amount(actual) == _parse_amount(expected) else 0.0
    except (InvalidOperation, ValueError):
        return 0.0


def _parse_amount(value: str) -> Decimal:
    value = value.strip().replace(" ", "")
    if "," in value:
        # Vírgula é separador decimal; pontos, se existirem, são de milhar.
        value = value.replace(".", "").replace(",", ".")
    return Decimal(value)
