from dataclasses import dataclass, replace

from app.evaluation.trajectory import Trajectory


@dataclass(frozen=True)
class EvaluationResult:
    case_name: str
    expected: Trajectory
    actual: Trajectory

    @property
    def passed(self) -> bool:
        expected = self.expected
        actual = self.actual
        if expected.event_names is None:
            expected = replace(expected, event_names=None)
            actual = replace(actual, event_names=None)
        if expected.error_code is None:
            expected = replace(expected, error_code=None)
            actual = replace(actual, error_code=None)
        return expected == actual


@dataclass(frozen=True)
class RoutingScore:
    """Per-case routing dimensions. Does not include generated answer text."""

    action_match: bool
    tool_match: bool
    arguments_match: bool
    failure_match: bool


@dataclass(frozen=True)
class RoutingAccuracy:
    case_count: int
    action_accuracy: float
    tool_accuracy: float
    argument_accuracy: float
    failure_accuracy: float


def score_routing(expected: Trajectory, actual: Trajectory) -> RoutingScore:
    return RoutingScore(
        action_match=expected.action == actual.action,
        tool_match=expected.tool_name == actual.tool_name,
        arguments_match=expected.tool_arguments == actual.tool_arguments,
        failure_match=expected.failure_class == actual.failure_class,
    )


def routing_accuracy(
    results: tuple[EvaluationResult, ...] | list[EvaluationResult],
) -> RoutingAccuracy:
    scored = tuple(score_routing(item.expected, item.actual) for item in results)
    count = len(scored)
    if count == 0:
        return RoutingAccuracy(
            case_count=0,
            action_accuracy=0.0,
            tool_accuracy=0.0,
            argument_accuracy=0.0,
            failure_accuracy=0.0,
        )
    return RoutingAccuracy(
        case_count=count,
        action_accuracy=sum(item.action_match for item in scored) / count,
        tool_accuracy=sum(item.tool_match for item in scored) / count,
        argument_accuracy=sum(item.arguments_match for item in scored) / count,
        failure_accuracy=sum(item.failure_match for item in scored) / count,
    )


def routing_agreement(
    left: tuple[EvaluationResult, ...] | list[EvaluationResult],
    right: tuple[EvaluationResult, ...] | list[EvaluationResult],
) -> RoutingAccuracy:
    """Compare two strategy actuals pairwise. Order must match."""
    paired = []
    for first, second in zip(left, right, strict=True):
        paired.append(
            EvaluationResult(
                case_name=first.case_name,
                expected=first.actual,
                actual=second.actual,
            )
        )
    return routing_accuracy(paired)
