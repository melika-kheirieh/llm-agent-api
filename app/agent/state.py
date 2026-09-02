from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from app.agent.observation import Observation
from app.agent.recovery import RecoveryAction
from app.infra.errors import FailureClass
from app.observability.events import TraceEvent, TraceEventName, append_event


class AgentStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass(frozen=True)
class AgentState:
    request: Any
    decision: Any = None
    tool_result: Any = None
    verification_result: bool | None = None
    attempts: int = 0
    observations: tuple[Observation, ...] = ()
    recovery_decision: RecoveryAction | None = None
    failure_class: FailureClass | None = None
    events: tuple[TraceEvent, ...] = ()
    status: AgentStatus = AgentStatus.CREATED

    def record(self, name: TraceEventName | str, **metadata: Any) -> "AgentState":
        return replace(self, events=append_event(self.events, name, **metadata))
