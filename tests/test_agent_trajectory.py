from app.agent.trajectory import (
    TrajectoryStatus,
    execute_maintenance_trajectory,
)


def test_verified_maintenance_trajectory():
    result = execute_maintenance_trajectory(
        "Show work order status"
    )

    assert result.status == TrajectoryStatus.COMPLETED


def test_unverified_request_requires_review():
    result = execute_maintenance_trajectory("Unknown request")

    assert result.status == TrajectoryStatus.NEEDS_HUMAN_REVIEW
