import asyncio

from app.agent.contracts import AgentAction
from app.agent.state import AgentStatus
from app.evaluation.agent_cases import DEFAULT_CASES
from app.evaluation.runner import run_case
from app.evaluation.trajectory import Trajectory


def _case(name: str):
    return next(c for c in DEFAULT_CASES if c.name == name)


def test_default_cases_cover_required_trajectories():
    names = {case.name for case in DEFAULT_CASES}
    assert names >= {
        "direct_answer_path",
        "successful_work_order_lookup",
        "missing_work_order_id",
        "invalid_verification_payload",
        "retryable_tool_failure",
        "non_retryable_tool_failure",
        "malformed_tool_result",
        "wrong_tool_selection",
        "retry_exhaustion",
    }


def test_evaluation_direct_answer_path():
    result = asyncio.run(run_case(_case("direct_answer_path")))

    assert result.actual.action == AgentAction.DIRECT.value
    assert result.actual.tool_name is None
    assert result.actual.tool_arguments is None
    assert result.actual.verification_result is None
    assert result.actual.attempts == 0
    assert result.actual.recovery_decision is None
    assert result.actual.terminal_status == AgentStatus.COMPLETED.value
    assert result.passed


def test_evaluation_successful_work_order_lookup():
    result = asyncio.run(run_case(_case("successful_work_order_lookup")))

    assert result.actual.action == AgentAction.USE_TOOL.value
    assert result.actual.tool_name == "work_order_lookup"
    assert result.actual.tool_arguments == {"work_order_id": "WO-123"}
    assert result.actual.verification_result is True
    assert result.actual.attempts == 1
    assert result.actual.recovery_decision is None
    assert result.actual.failure_class is None
    assert result.passed


def test_evaluation_missing_work_order_id():
    result = asyncio.run(run_case(_case("missing_work_order_id")))

    assert result.actual.tool_arguments == {}
    assert result.actual.verification_result is False
    assert result.actual.recovery_decision == "fail"
    assert result.actual.failure_class == "verification_failed"
    assert result.actual.terminal_status == AgentStatus.NEEDS_HUMAN_REVIEW.value
    assert result.passed


def test_evaluation_does_not_score_response_text():
    assert not any(
        field == "response_text"
        for field in Trajectory.__dataclass_fields__
    )
