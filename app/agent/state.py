from dataclasses import dataclass
from enum import Enum
from typing import Any


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
    status: AgentStatus = AgentStatus.CREATED
