import asyncio
import json
import os
import warnings
from pathlib import Path

from deepeval import evaluate
from deepeval.dataset import Golden
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig, ErrorConfig
from deepeval.test_case import LLMTestCase
from dotenv import load_dotenv

from eval.evaluate_expense_adaptor import evaluate_expense_exctraction
from eval.json_correctness_metric import (
    build_correctness_metrics,
    build_json_correctness_metric,
)

warnings.filterwarnings("ignore")

DATASET = Path(__file__).resolve().parent / "dataset/golden.json"
DEFAULT_PER_TASK_TIMEOUT_SECONDS = "180"


def load_golden_dataset() -> list[Golden]:
    records = json.loads(DATASET.read_text(encoding="utf-8"))
    return [Golden(**record) for record in records]


async def build_tests_cases(golden_dataset: list[Golden]) -> list[LLMTestCase]:
    tests = []
    for record in golden_dataset:
        actual_output = await evaluate_expense_exctraction(record.input)
        tests.append(
            LLMTestCase(
                name=record.name,
                input=record.input,
                actual_output=actual_output,
                expected_output=record.expected_output,
            )
        )

    return tests


async def main() -> None:
    load_dotenv()
    os.environ.setdefault(
        "DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE",
        DEFAULT_PER_TASK_TIMEOUT_SECONDS,
    )

    golden_dataset = load_golden_dataset()
    tests_cases = await build_tests_cases(golden_dataset)
    metric_json = build_json_correctness_metric()
    metric_geval = build_correctness_metrics()

    eval_result = evaluate(
        test_cases=tests_cases,
        metrics=[metric_json, metric_geval],
        async_config=AsyncConfig(
            run_async=True,
            max_concurrent=2,
            throttle_value=1,
        ),
        cache_config=CacheConfig(
            use_cache=True,
            write_cache=True,
        ),
        display_config=DisplayConfig(
            show_indicator=True,
            print_results=True,
            verbose_mode=True,
            file_type="md",
            file_output_dir=os.getenv("DEEPEVAL_RESULTS_FOLDER", "./evals"),
        ),
        error_config=ErrorConfig(
            ignore_errors=True,
            skip_on_missing_params=False,
        ),
    )

    print(eval_result)


if __name__ == "__main__":
    asyncio.run(main())
