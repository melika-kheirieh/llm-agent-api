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
        "model_timeout",
        "tool_timeout",
        "llm_chooses_direct",
        "llm_chooses_work_order_lookup",
        "llm_malformed_structured_output",
        "llm_invalid_tool_selection",
        "llm_invalid_arguments",
        "successful_maintenance_policy_lookup",
        "cross_tenant_work_order",
        "wrong_property_work_order",
        "missing_work_order",
        "stale_policy",
        "missing_policy",
        "wrong_tool_trap",
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
    assert result.actual.error_code is None
    assert result.passed


def test_evaluation_missing_work_order_id():
    result = asyncio.run(run_case(_case("missing_work_order_id")))

    assert result.actual.tool_arguments == {}
    assert result.actual.verification_result is False
    assert result.actual.recovery_decision == "fail"
    assert result.actual.failure_class == "tool_error"
    assert result.actual.terminal_status == AgentStatus.NEEDS_HUMAN_REVIEW.value
    assert result.passed


def test_evaluation_does_not_score_response_text():
    assert not any(
        field == "response_text"
        for field in Trajectory.__dataclass_fields__
    )


def test_evaluation_distinguishes_scope_rejection_from_timeout():
    cross_tenant = asyncio.run(run_case(_case("cross_tenant_work_order")))
    wrong_property = asyncio.run(run_case(_case("wrong_property_work_order")))
    timeout = asyncio.run(run_case(_case("tool_timeout")))

    assert cross_tenant.passed
    assert wrong_property.passed
    assert timeout.passed
    assert cross_tenant.actual.failure_class == "tool_error"
    assert wrong_property.actual.failure_class == "tool_error"
    assert timeout.actual.failure_class == "tool_timeout"
    assert cross_tenant.actual.error_code == "cross_tenant"
    assert wrong_property.actual.error_code == "wrong_property"
    assert timeout.actual.error_code == "tool_timeout"
    assert cross_tenant.actual.error_code != timeout.actual.error_code
