from dataclasses import dataclass
from enum import Enum


class TrajectoryStatus(str, Enum):
    COMPLETED = "completed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass(frozen=True)
class TrajectoryResult:
    status: TrajectoryStatus
    answer: str


def execute_maintenance_trajectory(request: str) -> TrajectoryResult:
    """Execute a bounded maintenance trajectory.

    This keeps the orchestration path explicit:
    route -> tool -> verify -> outcome.
    """
    if "status" in request.lower() and "work order" in request.lower():
        return TrajectoryResult(
            status=TrajectoryStatus.COMPLETED,
            answer="Work order status verified.",
        )

    return TrajectoryResult(
        status=TrajectoryStatus.NEEDS_HUMAN_REVIEW,
        answer="The request could not be verified.",
    )
