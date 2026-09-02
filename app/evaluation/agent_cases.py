from dataclasses import dataclass

from app.agent.state import AgentStatus


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    message: str
    expected_status: str


DEFAULT_CASES = [
    EvaluationCase(
        name="successful_tool_flow",
        message="Check work order WO-123",
        expected_status=AgentStatus.COMPLETED.value,
    ),
    EvaluationCase(
        name="verification_failure",
        message="Need maintenance help",
        expected_status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
    ),
    EvaluationCase(
        name="direct_llm_path",
        message="hello there",
        expected_status=AgentStatus.COMPLETED.value,
    ),
]
