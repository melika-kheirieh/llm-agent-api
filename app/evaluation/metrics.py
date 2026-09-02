from dataclasses import dataclass, replace

from app.evaluation.trajectory import Trajectory


@dataclass(frozen=True)
class EvaluationResult:
    case_name: str
    expected: Trajectory
    actual: Trajectory

    @property
    def passed(self) -> bool:
        if self.expected.event_names is None:
            return replace(self.expected, event_names=None) == replace(
                self.actual, event_names=None
            )
        return self.expected == self.actual
