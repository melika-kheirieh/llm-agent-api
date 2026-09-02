from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import ContextPolicy
from app.agent.contracts import AgentAction
from app.agent.recovery import RecoveryPolicy
from app.agent.router import AgentRouter
from app.agent.state import AgentState
from app.agent.tools import AgentTool, ToolResult
from app.agent.verification import ToolVerifier
from app.evaluation.agent_cases import EvaluationCase
from app.evaluation.metrics import EvaluationResult
from app.evaluation.trajectory import Trajectory
from app.infra.config import settings
from app.observability.trace import trace_from_state
from app.tools.work_order import WorkOrderLookupTool


class _EvaluationLLM:
    async def generate(self, prompt: str) -> str:
        return "direct evaluation answer"


class ScriptedTool:
    """Deterministic fake tool for evaluation cases. No external I/O."""

    name = "work_order_lookup"

    def __init__(self, results: tuple[ToolResult, ...] | list[ToolResult]):
        self._results = list(results)
        self.calls: list[dict] = []

    async def execute(self, arguments: dict) -> ToolResult:
        self.calls.append(arguments)
        index = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[index]


def _tools_for_case(case: EvaluationCase) -> dict[str, AgentTool] | None:
    if case.omit_tools:
        return {}
    if case.tool_results is not None:
        scripted = ScriptedTool(case.tool_results)
        return {scripted.name: scripted}
    return None


def build_evaluation_runtime(
    tools: dict[str, AgentTool] | None = None,
) -> AsyncAgentRuntime:
    """Same agent wiring as production, with a fake LLM provider."""
    from app.infra.container import build_runtime

    return build_runtime(llm=_EvaluationLLM(), tools=tools)


def _runtime_for_case(case: EvaluationCase) -> AsyncAgentRuntime:
    timeout = float(settings.llm_timeout_seconds)
    tools = _tools_for_case(case)
    if tools is None:
        work_order = WorkOrderLookupTool()
        tools = {work_order.name: work_order}
    return AsyncAgentRuntime(
        _EvaluationLLM(),
        timeout_seconds=timeout,
        router=AgentRouter(),
        tools=tools,
        verifier=ToolVerifier(),
        recovery=RecoveryPolicy(max_attempts=2),
        context_policy=ContextPolicy(),
    )


def trajectory_from_state(state: AgentState) -> Trajectory:
    trace = trace_from_state(state)
    decision = state.decision
    arguments = None
    if decision is not None and decision.action == AgentAction.USE_TOOL:
        arguments = decision.arguments if decision.arguments is not None else {}
    recovery = None
    if state.recovery_decision is not None:
        recovery = state.recovery_decision.value
    return Trajectory(
        action=trace.decision,
        tool_name=trace.selected_tool,
        tool_arguments=arguments,
        verification_result=state.verification_result,
        failure_class=trace.failure_class,
        attempts=trace.attempts,
        recovery_decision=recovery,
        outcome=trace.outcome,
        terminal_status=trace.terminal_status,
    )


async def run_case(
    case: EvaluationCase,
    runtime: AsyncAgentRuntime | None = None,
) -> EvaluationResult:
    agent = runtime or _runtime_for_case(case)
    _answer, state = await agent.run_detailed(case.message)
    return EvaluationResult(
        case_name=case.name,
        expected=case.expected,
        actual=trajectory_from_state(state),
    )
