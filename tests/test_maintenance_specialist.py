from app.specialists.maintenance import MaintenanceSpecialist


def test_maintenance_specialist_returns_typed_assessment():
    result = MaintenanceSpecialist().assess("plumbing")

    assert result.issue_type == "plumbing"
    assert result.urgency == "unknown"
