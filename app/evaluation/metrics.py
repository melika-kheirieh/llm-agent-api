from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationResult:
    case_name: str
    expected_status: str
    actual_status: str

    @property
    def passed(self) -> bool:
        return self.expected_status == self.actual_status
