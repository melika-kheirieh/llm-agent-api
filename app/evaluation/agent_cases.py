from dataclasses import dataclass

from app.agent.context import TrustedScope
from app.agent.contracts import AgentAction
from app.agent.state import AgentStatus
from app.agent.tools import ToolResult
from app.evaluation.trajectory import Trajectory
from app.infra.errors import FailureClass
from app.observability.events import TraceEventName as E
from app.tools.catalog import DEFAULT_SCOPE, scoped_work_order_data


DIRECT_SUCCESS_EVENTS = (
    E.RUN_STARTED.value,
    E.ROUTE_SELECTED.value,
    E.RUN_COMPLETED.value,
)
TOOL_SUCCESS_EVENTS = (
    E.RUN_STARTED.value,
    E.ROUTE_SELECTED.value,
    E.TOOL_STARTED.value,
    E.TOOL_COMPLETED.value,
    E.VERIFICATION_COMPLETED.value,
    E.RUN_COMPLETED.value,
)
RETRY_THEN_SUCCESS_EVENTS = (
    E.RUN_STARTED.value,
    E.ROUTE_SELECTED.value,
    E.TOOL_STARTED.value,
    E.TOOL_FAILED.value,
    E.VERIFICATION_COMPLETED.value,
    E.RECOVERY_DECISION.value,
    E.TOOL_STARTED.value,
    E.TOOL_COMPLETED.value,
    E.VERIFICATION_COMPLETED.value,
    E.RUN_COMPLETED.value,
)
TOOL_FAILURE_EVENTS = (
    E.RUN_STARTED.value,
    E.ROUTE_SELECTED.value,
    E.TOOL_STARTED.value,
    E.TOOL_FAILED.value,
    E.VERIFICATION_COMPLETED.value,
    E.RECOVERY_DECISION.value,
    E.RUN_FAILED.value,
)
MODEL_FAILURE_EVENTS = (
    E.RUN_STARTED.value,
    E.ROUTE_SELECTED.value,
    E.RUN_FAILED.value,
)
ROUTE_PARSE_FAILURE_EVENTS = (
    E.RUN_STARTED.value,
    E.RUN_FAILED.value,
)


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    message: str
    expected: Trajectory
    tool_results: tuple[ToolResult, ...] | None = None
    omit_tools: bool = False
    model_mode: str = "ok"
    model_timeout_seconds: float | None = None
    tool_timeout_seconds: float | None = None
    tool_delay_seconds: float | None = None
    router_kind: str = "keyword"
    route_output: str | None = None
    trusted_scope: TrustedScope | None = None
    scripted_tool_name: str = "work_order_lookup"


DEFAULT_CASES = [
    EvaluationCase(
        name="direct_answer_path",
        message="hello there",
        expected=Trajectory(
            action=AgentAction.DIRECT.value,
            tool_name=None,
            tool_arguments=None,
            verification_result=None,
            failure_class=None,
            attempts=0,
            recovery_decision=None,
            outcome="success",
            terminal_status=AgentStatus.COMPLETED.value,
            event_names=DIRECT_SUCCESS_EVENTS,
        ),
    ),
    EvaluationCase(
        name="successful_work_order_lookup",
        message="Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=True,
            failure_class=None,
            attempts=1,
            recovery_decision=None,
            outcome="success",
            terminal_status=AgentStatus.COMPLETED.value,
            event_names=TOOL_SUCCESS_EVENTS,
        ),
    ),
    EvaluationCase(
        name="missing_work_order_id",
        message="Need maintenance help",
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            event_names=TOOL_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="invalid_verification_payload",
        message="Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
        tool_results=(
            ToolResult(
                success=True,
                data={
                    **scoped_work_order_data(),
                    "status": "lost",
                },
            ),
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=False,
            failure_class=FailureClass.VERIFICATION_FAILURE.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="retryable_tool_failure",
        message="Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
        tool_results=(
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(
                success=True,
                data=scoped_work_order_data(),
            ),
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=True,
            failure_class=None,
            attempts=2,
            recovery_decision="retry",
            outcome="success",
            terminal_status=AgentStatus.COMPLETED.value,
            event_names=RETRY_THEN_SUCCESS_EVENTS,
        ),
    ),
    EvaluationCase(
        name="non_retryable_tool_failure",
        message="Check work order WO-123",
        tool_results=(
            ToolResult(
                success=False,
                data={"error": "not_found"},
                retryable=False,
            ),
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="malformed_tool_result",
        message="Check work order WO-123",
        tool_results=(
            ToolResult(success=True, data={"work_order_id": "WO-123"}),
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=False,
            failure_class=FailureClass.VERIFICATION_FAILURE.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="wrong_tool_selection",
        message="Check work order WO-123",
        omit_tools=True,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=None,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="retry_exhaustion",
        message="Check work order WO-123",
        tool_results=(
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=2,
            recovery_decision="escalate",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="model_timeout",
        message="hello there",
        model_mode="timeout",
        model_timeout_seconds=0.05,
        expected=Trajectory(
            action=AgentAction.DIRECT.value,
            tool_name=None,
            tool_arguments=None,
            verification_result=None,
            failure_class=FailureClass.MODEL_TIMEOUT.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=MODEL_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="tool_timeout",
        message="Check work order WO-123",
        tool_delay_seconds=0.2,
        tool_timeout_seconds=0.05,
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=False,
            failure_class=FailureClass.TOOL_TIMEOUT.value,
            attempts=2,
            recovery_decision="escalate",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            error_code="tool_timeout",
        ),
    ),
    EvaluationCase(
        name="llm_chooses_direct",
        message="Check work order WO-123",
        router_kind="llm",
        route_output='{"action": "direct", "tool_name": null, "arguments": null}',
        expected=Trajectory(
            action=AgentAction.DIRECT.value,
            tool_name=None,
            tool_arguments=None,
            verification_result=None,
            failure_class=None,
            attempts=0,
            recovery_decision=None,
            outcome="success",
            terminal_status=AgentStatus.COMPLETED.value,
            event_names=DIRECT_SUCCESS_EVENTS,
        ),
    ),
    EvaluationCase(
        name="llm_chooses_work_order_lookup",
        message="hello there",
        router_kind="llm",
        trusted_scope=DEFAULT_SCOPE,
        route_output=(
            '{"action": "use_tool", "tool_name": "work_order_lookup", '
            '"arguments": {"work_order_id": "WO-123"}}'
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=True,
            failure_class=None,
            attempts=1,
            recovery_decision=None,
            outcome="success",
            terminal_status=AgentStatus.COMPLETED.value,
            event_names=TOOL_SUCCESS_EVENTS,
        ),
    ),
    EvaluationCase(
        name="llm_malformed_structured_output",
        message="hello there",
        router_kind="llm",
        route_output="not a routing object",
        expected=Trajectory(
            action=None,
            tool_name=None,
            tool_arguments=None,
            verification_result=None,
            failure_class=FailureClass.MODEL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=ROUTE_PARSE_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="llm_invalid_tool_selection",
        message="hello there",
        router_kind="llm",
        route_output=(
            '{"action": "use_tool", "tool_name": "billing_lookup", "arguments": {}}'
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="billing_lookup",
            tool_arguments={},
            verification_result=None,
            failure_class=FailureClass.MODEL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=MODEL_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="llm_invalid_arguments",
        message="hello there",
        router_kind="llm",
        route_output=(
            '{"action": "use_tool", "tool_name": "work_order_lookup", '
            '"arguments": {"work_order_id": 123}}'
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": 123},
            verification_result=None,
            failure_class=FailureClass.MODEL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="failure",
            terminal_status=AgentStatus.FAILED.value,
            event_names=MODEL_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="successful_maintenance_policy_lookup",
        message="Check maintenance policy for plumbing",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="maintenance_policy_lookup",
            tool_arguments={"issue_type": "plumbing"},
            verification_result=True,
            failure_class=None,
            attempts=1,
            recovery_decision=None,
            outcome="success",
            terminal_status=AgentStatus.COMPLETED.value,
            event_names=TOOL_SUCCESS_EVENTS,
        ),
    ),
    EvaluationCase(
        name="cross_tenant_work_order",
        message="Check work order WO-999",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-999"},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            event_names=TOOL_FAILURE_EVENTS,
            error_code="cross_tenant",
        ),
    ),
    EvaluationCase(
        name="wrong_property_work_order",
        message="Check work order WO-456",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-456"},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            event_names=TOOL_FAILURE_EVENTS,
            error_code="wrong_property",
        ),
    ),
    EvaluationCase(
        name="missing_work_order",
        message="Check work order WO-404",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-404"},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            event_names=TOOL_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="stale_policy",
        message="Check maintenance policy for hvac",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="maintenance_policy_lookup",
            tool_arguments={"issue_type": "hvac"},
            verification_result=False,
            failure_class=FailureClass.VERIFICATION_FAILURE.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="missing_policy",
        message="Check maintenance policy for roofing",
        trusted_scope=DEFAULT_SCOPE,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="maintenance_policy_lookup",
            tool_arguments={"issue_type": "roofing"},
            verification_result=False,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            event_names=TOOL_FAILURE_EVENTS,
        ),
    ),
    EvaluationCase(
        name="wrong_tool_trap",
        message="Check maintenance policy for plumbing",
        omit_tools=True,
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="maintenance_policy_lookup",
            tool_arguments={"issue_type": "plumbing"},
            verification_result=None,
            failure_class=FailureClass.TOOL_ERROR.value,
            attempts=0,
            recovery_decision=None,
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
]
