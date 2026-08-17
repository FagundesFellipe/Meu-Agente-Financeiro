import json

import pytest
from deepeval.test_case import LLMTestCase

from eval.json_correctness_metric import (
    ExpenseExtractionCorrectnessMetric,
    build_json_correctness_metric,
    build_value_correctness_metric,
)


def _case(actual, expected) -> LLMTestCase:
    return LLMTestCase(
        input="gasto de teste",
        actual_output=json.dumps(actual, ensure_ascii=False),
        expected_output=json.dumps(expected, ensure_ascii=False),
    )


def _expense(**overrides) -> dict:
    payload = {
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
    return payload


def _result(**overrides) -> dict:
    payload = {
        "expenses": [_expense()],
        "needs_clarification": False,
        "clarification_message": None,
    }
    payload.update(overrides)
    return payload


class TestExpenseExtractionCorrectnessMetric:
    @pytest.fixture
    def metric(self):
        return ExpenseExtractionCorrectnessMetric()

    def test_perfect_match_scores_one(self, metric):
        expected = _result()
        metric.measure(_case(expected, expected))
        assert metric.score == 1.0
        assert metric.is_successful()

    def test_wrong_amount_lowers_score(self, metric):
        actual = _result(expenses=[_expense(amount_raw="40")])
        expected = _result()
        metric.measure(_case(actual, expected))
        # 0.25 de peso * 0 = 0.25 a menos no score do gasto; gasto vale 80%.
        assert metric.score == pytest.approx(0.80, abs=0.05)

    def test_wrong_category_lowers_score(self, metric):
        actual = _result(expenses=[_expense(category_hint="Transporte")])
        expected = _result()
        metric.measure(_case(actual, expected))
        # 0.10 de peso * 0 = 0.10 a menos no score do gasto; gasto vale 80%.
        assert metric.score == pytest.approx(0.92, abs=0.05)

    def test_amount_formatting_differences_are_normalized(self, metric):
        actual = _result(expenses=[_expense(amount_raw="35,00")])
        expected = _result()
        metric.measure(_case(actual, expected))
        assert metric.score == 1.0

    def test_description_similarity_gives_partial_credit(self, metric):
        actual = _result(expenses=[_expense(description="almoço de hoje")])
        expected = _result()
        metric.measure(_case(actual, expected))
        assert 0.0 < metric.score < 1.0

    def test_missing_expense_penalizes_size_difference(self, metric):
        actual = _result(expenses=[])
        expected = _result(
            expenses=[
                _expense(),
                _expense(
                    description="táxi",
                    amount_raw="40",
                    category_hint="Transporte",
                ),
            ]
        )
        metric.measure(_case(actual, expected))
        assert metric.score == 0.0

    def test_clarification_flag_match_with_different_message(self, metric):
        actual = _result(
            expenses=[],
            needs_clarification=True,
            clarification_message="Qual foi o valor do almoço?",
        )
        expected = _result(
            expenses=[],
            needs_clarification=True,
            clarification_message="Quanto você gastou no almoço?",
        )
        metric.measure(_case(actual, expected))
        # 20% pelo flag + 20% * similaridade da mensagem + 60% * expenses vazio.
        assert 0.2 < metric.score < 1.0

    def test_wrong_needs_clarification_flag_hurts_score(self, metric):
        actual = _result(
            expenses=[_expense()],
            needs_clarification=False,
            clarification_message=None,
        )
        expected = _result(
            expenses=[],
            needs_clarification=True,
            clarification_message="Qual foi o valor?",
        )
        metric.measure(_case(actual, expected))
        assert metric.score < 0.5

    def test_multiple_expenses_are_scored_together(self, metric):
        actual = _result(
            expenses=[
                _expense(description="café", amount_raw="25"),
                _expense(
                    description="táxi",
                    amount_raw="40",
                    category_hint="Transporte",
                ),
            ]
        )
        expected = actual
        metric.measure(_case(actual, expected))
        assert metric.score == 1.0


class TestMetricBuilders:
    def test_build_json_correctness_metric_returns_metric(self):
        metric = build_json_correctness_metric()
        assert metric.__name__ == "JSON Correctness"

    def test_build_value_correctness_metric_returns_metric(self):
        metric = build_value_correctness_metric()
        assert metric.__name__ == "Expense Extraction Correctness"
