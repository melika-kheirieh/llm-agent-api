from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from time import time

from app.agent.contracts import AgentAction
from app.agent.state import AgentState, AgentStatus


@dataclass
class TraceEvent:
    name: str
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class ExecutionTrace:
    run_id: str
    request_id: str
    terminal_status: str
    decision: str | None = None
    selected_tool: str | None = None
    verification_result: str | None = None
    attempts: int = 0
    retry_count: int = 0
    outcome: str = "success"
    failure_class: str | None = None
    thread_id: str | None = None
    recovery_decision: str | None = None

    def as_log_fields(self) -> dict:
        return {
            "run_id": self.run_id,
            "terminal_status": self.terminal_status,
            "decision": self.decision,
            "selected_tool": self.selected_tool,
            "verification_result": self.verification_result,
            "attempts": self.attempts,
            "retry_count": self.retry_count,
            "outcome": self.outcome,
            "failure_class": self.failure_class,
            "recovery_decision": self.recovery_decision,
        }


def trace_from_state(state: AgentState, run_id: str | None = None) -> ExecutionTrace:
    """Map a finished AgentState into a lightweight execution trace."""
    trace_id = run_id or str(uuid.uuid4())
    decision = state.decision
    action = decision.action.value if decision is not None else None
    tool_name = None
    if decision is not None and decision.action == AgentAction.USE_TOOL:
        tool_name = decision.tool_name

    verification = None
    if state.verification_result is not None:
        verification = str(state.verification_result).lower()

    attempts = state.attempts
    retry_count = max(attempts - 1, 0)

    if state.status == AgentStatus.COMPLETED:
        outcome = "success"
    elif state.status == AgentStatus.NEEDS_HUMAN_REVIEW:
        outcome = "needs_human_review"
    elif state.status == AgentStatus.FAILED:
        outcome = "failure"
    else:
        outcome = state.status.value

    failure_class = None
    if state.failure_class is not None:
        failure_class = state.failure_class.value

    return ExecutionTrace(
        run_id=trace_id,
        request_id=trace_id,
        terminal_status=state.status.value,
        decision=action,
        selected_tool=tool_name,
        verification_result=verification,
        attempts=attempts,
        retry_count=retry_count,
        outcome=outcome,
        failure_class=failure_class,
        recovery_decision=(
            state.recovery_decision.value if state.recovery_decision is not None else None
        ),
    )
