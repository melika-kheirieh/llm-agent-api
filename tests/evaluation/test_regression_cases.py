import asyncio

from app.evaluation.agent_cases import DEFAULT_CASES
from app.evaluation.metrics import EvaluationResult
from app.evaluation.runner import build_evaluation_runtime, run_case


def test_evaluation_result_compares_status():
    result = EvaluationResult(
        case_name="successful_execution",
        expected_status="completed",
        actual_status="completed",
    )
    assert result.passed


def test_default_cases_execute_against_runtime():
    runtime = build_evaluation_runtime()

    async def _run():
        return [await run_case(case, runtime) for case in DEFAULT_CASES]

    results = asyncio.run(_run())

    assert results
    assert all(result.passed for result in results)
