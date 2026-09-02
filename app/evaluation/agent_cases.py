from dataclasses import dataclass

from app.agent.contracts import AgentAction
from app.agent.state import AgentStatus
from app.agent.tools import ToolResult
from app.evaluation.trajectory import Trajectory


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    message: str
    expected: Trajectory
    tool_results: tuple[ToolResult, ...] | None = None
    omit_tools: bool = False


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
        ),
    ),
    EvaluationCase(
        name="successful_work_order_lookup",
        message="Check work order WO-123",
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
            failure_class="verification_failed",
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="invalid_verification_payload",
        message="Check work order WO-123",
        tool_results=(
            ToolResult(
                success=True,
                data={
                    "work_order_id": "WO-123",
                    "status": "lost",
                    "issue_type": "plumbing",
                },
            ),
        ),
        expected=Trajectory(
            action=AgentAction.USE_TOOL.value,
            tool_name="work_order_lookup",
            tool_arguments={"work_order_id": "WO-123"},
            verification_result=False,
            failure_class="verification_failed",
            attempts=1,
            recovery_decision="fail",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
    EvaluationCase(
        name="retryable_tool_failure",
        message="Check work order WO-123",
        tool_results=(
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(
                success=True,
                data={
                    "work_order_id": "WO-123",
                    "status": "open",
                    "issue_type": "plumbing",
                },
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
            failure_class="verification_failed",
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
            failure_class="verification_failed",
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
            failure_class="needs_review",
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
            failure_class="verification_failed",
            attempts=2,
            recovery_decision="escalate",
            outcome="needs_human_review",
            terminal_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
        ),
    ),
]
