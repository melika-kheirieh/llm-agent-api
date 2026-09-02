import asyncio

from app.evaluation.agent_cases import DEFAULT_CASES
from app.evaluation.metrics import EvaluationResult
from app.evaluation.runner import run_case
from app.evaluation.trajectory import Trajectory


def test_evaluation_result_compares_full_trajectory():
    matching = EvaluationResult(
        case_name="successful_work_order_lookup",
        expected=Trajectory(
            action="use_tool",
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=True,
            attempts=1,
            outcome="success",
            terminal_status="completed",
        ),
        actual=Trajectory(
            action="use_tool",
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=True,
            attempts=1,
            outcome="success",
            terminal_status="completed",
        ),
    )
    mismatched_action = EvaluationResult(
        case_name="successful_work_order_lookup",
        expected=Trajectory(action="use_tool", terminal_status="completed"),
        actual=Trajectory(action="direct", terminal_status="completed"),
    )
    mismatched_arguments = EvaluationResult(
        case_name="successful_work_order_lookup",
        expected=Trajectory(
            action="use_tool",
            tool_arguments={"work_order_id": "WO-123"},
        ),
        actual=Trajectory(
            action="use_tool",
            tool_arguments={"work_order_id": "WO-999"},
        ),
    )
    assert matching.passed
    assert not mismatched_action.passed
    assert not mismatched_arguments.passed


def test_evaluation_result_event_names_are_optional():
    expected = Trajectory(action="direct", terminal_status="completed")
    actual = Trajectory(
        action="direct",
        terminal_status="completed",
        event_names=("run_started", "route_selected", "run_completed"),
    )
    assert EvaluationResult("direct", expected, actual).passed

    expected_events = Trajectory(
        action="direct",
        terminal_status="completed",
        event_names=("run_started", "run_completed"),
    )
    assert not EvaluationResult("direct", expected_events, actual).passed


def test_all_trajectory_cases_pass():
    async def _run():
        return [await run_case(case) for case in DEFAULT_CASES]

    results = asyncio.run(_run())

    assert len(results) == len(DEFAULT_CASES)
    failed = [result.case_name for result in results if not result.passed]
    assert failed == []


def test_invalid_verification_payload_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "invalid_verification_payload")
    result = asyncio.run(run_case(case))

    assert result.actual.verification_result is False
    assert result.actual.recovery_decision == "fail"
    assert result.actual.failure_class == "verification_failure"
    assert result.passed


def test_retryable_tool_failure_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "retryable_tool_failure")
    result = asyncio.run(run_case(case))

    assert result.actual.attempts == 2
    assert result.actual.recovery_decision == "retry"
    assert result.actual.verification_result is True
    assert result.actual.outcome == "success"
    assert result.passed


def test_non_retryable_tool_failure_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "non_retryable_tool_failure")
    result = asyncio.run(run_case(case))

    assert result.actual.attempts == 1
    assert result.actual.recovery_decision == "fail"
    assert result.actual.outcome == "needs_human_review"
    assert result.passed


def test_malformed_tool_result_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "malformed_tool_result")
    result = asyncio.run(run_case(case))

    assert result.actual.verification_result is False
    assert result.actual.recovery_decision == "fail"
    assert result.passed


def test_wrong_tool_selection_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "wrong_tool_selection")
    result = asyncio.run(run_case(case))

    assert result.actual.action == "use_tool"
    assert result.actual.tool_name == "work_order_lookup"
    assert result.actual.verification_result is None
    assert result.actual.attempts == 0
    assert result.actual.recovery_decision is None
    assert result.actual.failure_class == "tool_error"
    assert result.passed


def test_retry_exhaustion_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "retry_exhaustion")
    result = asyncio.run(run_case(case))

    assert result.actual.attempts == 2
    assert result.actual.recovery_decision == "escalate"
    assert result.actual.failure_class == "tool_error"
    assert result.passed


def test_model_timeout_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "model_timeout")
    result = asyncio.run(run_case(case))

    assert result.actual.action == "direct"
    assert result.actual.failure_class == "model_timeout"
    assert result.actual.terminal_status == "failed"
    assert result.actual.outcome == "failure"
    assert result.passed


def test_tool_timeout_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "tool_timeout")
    result = asyncio.run(run_case(case))

    assert result.actual.failure_class == "tool_timeout"
    assert result.actual.recovery_decision == "escalate"
    assert result.actual.attempts == 2
    assert result.actual.outcome == "needs_human_review"
    assert result.passed


def test_llm_chooses_direct_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "llm_chooses_direct")
    result = asyncio.run(run_case(case))

    assert result.actual.action == "direct"
    assert result.actual.tool_name is None
    assert result.actual.tool_arguments is None
    assert result.actual.outcome == "success"
    assert result.passed


def test_llm_chooses_work_order_lookup_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "llm_chooses_work_order_lookup")
    result = asyncio.run(run_case(case))

    assert result.actual.action == "use_tool"
    assert result.actual.tool_name == "work_order_lookup"
    assert result.actual.tool_arguments == {"work_order_id": "WO-123"}
    assert result.actual.outcome == "success"
    assert result.passed


def test_llm_malformed_structured_output_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "llm_malformed_structured_output")
    result = asyncio.run(run_case(case))

    assert result.actual.action is None
    assert result.actual.tool_name is None
    assert result.actual.tool_arguments is None
    assert result.actual.failure_class == "model_error"
    assert result.actual.outcome == "failure"
    assert result.passed


def test_llm_invalid_tool_selection_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "llm_invalid_tool_selection")
    result = asyncio.run(run_case(case))

    assert result.actual.action == "use_tool"
    assert result.actual.tool_name == "billing_lookup"
    assert result.actual.tool_arguments == {}
    assert result.actual.failure_class == "model_error"
    assert result.actual.outcome == "failure"
    assert result.passed


def test_llm_invalid_arguments_trajectory():
    case = next(c for c in DEFAULT_CASES if c.name == "llm_invalid_arguments")
    result = asyncio.run(run_case(case))

    assert result.actual.action == "use_tool"
    assert result.actual.tool_name == "work_order_lookup"
    assert result.actual.tool_arguments == {"work_order_id": 123}
    assert result.actual.failure_class == "model_error"
    assert result.actual.outcome == "failure"
    assert result.passed


def test_all_default_cases_pass():
    for case in DEFAULT_CASES:
        result = asyncio.run(run_case(case))
        assert result.passed, (case.name, result.expected, result.actual)
