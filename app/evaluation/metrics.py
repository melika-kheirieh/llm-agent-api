from dataclasses import dataclass

from app.evaluation.trajectory import Trajectory


@dataclass(frozen=True)
class EvaluationResult:
    case_name: str
    expected: Trajectory
    actual: Trajectory

    @property
    def passed(self) -> bool:
        return self.expected == self.actual
