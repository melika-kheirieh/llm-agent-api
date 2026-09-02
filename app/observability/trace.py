from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.agent.contracts import AgentAction
from app.agent.state import AgentState, AgentStatus
from app.observability.events import TraceEvent, TraceEventName, event_names


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
    router_type: str | None = None
    events: tuple[TraceEvent, ...] = ()

    def as_log_fields(self) -> dict:
        return {
            "run_id": self.run_id,
            "terminal_status": self.terminal_status,
            "decision": self.decision,
            "selected_tool": self.selected_tool,
            "router_type": self.router_type,
            "routing_ms": routing_duration_ms(self.events),
            "verification_result": self.verification_result,
            "attempts": self.attempts,
            "retry_count": self.retry_count,
            "outcome": self.outcome,
            "failure_class": self.failure_class,
            "recovery_decision": self.recovery_decision,
            "event_names": list(event_names(self.events)),
            "event_count": len(self.events),
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

    recovery_decision = None
    if state.recovery_decision is not None:
        recovery_decision = state.recovery_decision.value

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
        recovery_decision=recovery_decision,
        router_type=state.router_type,
        events=state.events,
    )


def routing_duration_ms(events: tuple[TraceEvent, ...]) -> float | None:
    """Elapsed time from run_started to route_selected. None if routing never completed."""
    started = None
    routed = None
    for event in events:
        if event.name == TraceEventName.RUN_STARTED.value and started is None:
            started = event
        elif event.name == TraceEventName.ROUTE_SELECTED.value and routed is None:
            routed = event
    if started is None or routed is None:
        return None
    return round((routed.timestamp - started.timestamp) * 1000, 2)
