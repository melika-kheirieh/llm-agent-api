from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    expected_status: str


DEFAULT_CASES = [
    EvaluationCase(name="successful_tool_flow", expected_status="completed"),
    EvaluationCase(name="verification_failure", expected_status="needs_human_review"),
]
