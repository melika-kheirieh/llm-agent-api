import asyncio

from app.agent.state import AgentStatus
from app.evaluation.agent_cases import DEFAULT_CASES
from app.evaluation.runner import build_evaluation_runtime, run_case


def test_default_cases_cover_success_review_and_direct():
    assert {case.expected_status for case in DEFAULT_CASES} == {
        AgentStatus.COMPLETED.value,
        AgentStatus.NEEDS_HUMAN_REVIEW.value,
    }
    assert {case.name for case in DEFAULT_CASES} >= {
        "successful_tool_flow",
        "verification_failure",
        "direct_llm_path",
    }


def test_evaluation_success_case_runs_runtime():
    case = next(c for c in DEFAULT_CASES if c.name == "successful_tool_flow")
    result = asyncio.run(run_case(case, build_evaluation_runtime()))

    assert result.actual_status == AgentStatus.COMPLETED.value
    assert result.passed


def test_evaluation_verification_failure_runs_runtime():
    case = next(c for c in DEFAULT_CASES if c.name == "verification_failure")
    result = asyncio.run(run_case(case, build_evaluation_runtime()))

    assert result.actual_status == AgentStatus.NEEDS_HUMAN_REVIEW.value
    assert result.passed


def test_evaluation_direct_path_runs_runtime():
    case = next(c for c in DEFAULT_CASES if c.name == "direct_llm_path")
    result = asyncio.run(run_case(case, build_evaluation_runtime()))

    assert result.actual_status == AgentStatus.COMPLETED.value
    assert result.passed
