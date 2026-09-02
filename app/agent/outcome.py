from dataclasses import dataclass
from enum import Enum


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass(frozen=True)
class AgentOutcome:
    status: OutcomeStatus
    answer: str | None = None
    reason: str | None = None
