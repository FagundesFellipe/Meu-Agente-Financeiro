import pytest
from deepeval.metrics import GEval, JsonCorrectnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams
from pydantic import ValidationError

from eval import json_correctness_metric
from financial_agent.agent.state_graph import AddExpensesResult


class TestMetricBuilders:
    def test_build_json_correctness_metric_configures_schema_metric(self):
        metric = json_correctness_metric.build_json_correctness_metric()

        assert isinstance(metric, JsonCorrectnessMetric)
        assert metric.expected_schema == AddExpensesResult(expenses=[])
        assert metric.strict_mode is True
        assert metric.async_mode is True
        assert metric.verbose_mode is True

    @pytest.mark.parametrize(
        ("actual_output", "expected_score"),
        [
            (
                '{"expenses": [], "pending_expenses": [], '
                '"needs_clarification": false, "clarification_message": null}',
                1,
            ),
            ('{"expenses": "não é uma lista"}', 0),
        ],
    )
    def test_json_metric_validates_real_output(self, actual_output, expected_score):
        metric = json_correctness_metric.build_json_correctness_metric()
        # A validação estrutural é local; evitar a justificativa LLM mantém o
        # teste determinístico e sem chamadas externas.
        metric.include_reason = False

        score = metric.measure(
            LLMTestCase(input="gasto de teste", actual_output=actual_output)
        )

        assert score == expected_score
        assert metric.score == expected_score

    def test_add_expenses_result_rejects_invalid_json(self):
        with pytest.raises(ValidationError):
            AddExpensesResult.model_validate_json('{"expenses": "inválido"}')

    def test_build_correctness_metrics_configures_semantic_geval(self):
        metric = json_correctness_metric.build_correctness_metrics()

        assert isinstance(metric, GEval)
        assert metric.name == "Field Correctness"
        assert metric.threshold == 0.7
        assert metric.async_mode is True
        assert metric.verbose_mode is True
        assert metric.evaluation_params == [
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ]
        assert "equivalência SEMÂNTICA" in metric.criteria
        assert "ignore completamente" in metric.criteria
        assert "date_hint" in metric.criteria
        assert "omitam gastos" in metric.criteria
        assert "inventem gastos inexistentes" in metric.criteria

        evaluation_steps = " ".join(metric.evaluation_steps)
        assert len(metric.evaluation_steps) == 6
        assert "Ignore completamente o campo date_hint" in evaluation_steps
        assert "Verifique a ambiguidade" in evaluation_steps

        assert [rubric.score_range for rubric in metric.rubric] == [
            (0, 2),
            (3, 5),
            (6, 8),
            (9, 10),
        ]
        assert "omissão de um gasto" in metric.rubric[0].expected_outcome
