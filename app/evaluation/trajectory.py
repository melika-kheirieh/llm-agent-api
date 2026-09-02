from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Trajectory:
    """Golden / actual control-loop path for one evaluation run.

    Does not include the chat response text. terminal_status is AgentStatus;
    outcome is the trace outcome (success | needs_human_review | failure).
    attempts is total tool executions (first try included).
    event_names is an optional ordered list of step event names; timestamps
    are never compared.
    """

    action: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    verification_result: bool | None = None
    failure_class: str | None = None
    attempts: int = 0
    recovery_decision: str | None = None
    outcome: str = "success"
    terminal_status: str | None = None
    event_names: tuple[str, ...] | None = None
