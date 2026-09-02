from app.agent.async_runtime import AsyncAgentRuntime
from app.evaluation.agent_cases import EvaluationCase
from app.evaluation.metrics import EvaluationResult
from app.infra.container import build_runtime


class _EvaluationLLM:
    async def generate(self, prompt: str) -> str:
        return "direct evaluation answer"


def build_evaluation_runtime() -> AsyncAgentRuntime:
    """Same agent wiring as production, with a fake LLM provider."""
    return build_runtime(llm=_EvaluationLLM())


async def run_case(
    case: EvaluationCase,
    runtime: AsyncAgentRuntime | None = None,
) -> EvaluationResult:
    agent = runtime or build_evaluation_runtime()
    _answer, state = await agent.run_detailed(case.message)
    return EvaluationResult(
        case_name=case.name,
        expected_status=case.expected_status,
        actual_status=state.status.value,
    )
