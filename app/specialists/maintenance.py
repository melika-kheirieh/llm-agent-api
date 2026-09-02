from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceAssessment:
    issue_type: str
    urgency: str
    action: str


class MaintenanceSpecialist:
    def assess(self, issue_type: str) -> MaintenanceAssessment:
        return MaintenanceAssessment(
            issue_type=issue_type,
            urgency="unknown",
            action="needs_verification",
        )
