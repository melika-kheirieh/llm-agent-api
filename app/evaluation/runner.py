import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import ContextPolicy
from app.agent.contracts import AgentAction
from app.agent.llm_router import ROUTING_PROMPT_MARKER, LlmAgentRouter
from app.agent.recovery import RecoveryPolicy
from app.agent.router import AgentRouter
from app.agent.state import AgentState
from app.agent.tools import AgentTool, ToolResult
from app.agent.verification import ToolVerifier
from app.evaluation.agent_cases import EvaluationCase
from app.evaluation.metrics import EvaluationResult
from app.evaluation.trajectory import Trajectory
from app.infra.config import settings
from app.infra.errors import AgentFailure, DatabaseError
from app.observability.events import event_names as names_of
from app.observability.trace import trace_from_state
from app.tools.work_order import WorkOrderLookupTool


class _EvaluationLLM:
    async def generate(self, prompt: str) -> str:
        return "direct evaluation answer"


class _TimeoutLLM:
    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(1.0)
        return "unreachable"


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


class DelayedScriptedTool(ScriptedTool):
    def __init__(
        self,
        results: tuple[ToolResult, ...] | list[ToolResult],
        delay_seconds: float,
    ):
        super().__init__(results)
        self.delay_seconds = delay_seconds

    async def execute(self, arguments: dict) -> ToolResult:
        await asyncio.sleep(self.delay_seconds)
        return await super().execute(arguments)


class _RoutingAwareLLM:
    def __init__(self, route_output: str, answer: str = "direct evaluation answer"):
        self.route_output = route_output
        self.answer = answer

    async def generate(self, prompt: str) -> str:
        if ROUTING_PROMPT_MARKER in prompt:
            return self.route_output
        return self.answer


def _llm_for_case(case: EvaluationCase):
    if case.model_mode == "timeout":
        return _TimeoutLLM()
    if case.router_kind == "llm":
        return _RoutingAwareLLM(case.route_output or "")
    return _EvaluationLLM()


def _tools_for_case(case: EvaluationCase) -> dict[str, AgentTool] | None:
    if case.omit_tools:
        return {}
    results = case.tool_results
    if case.tool_delay_seconds is not None:
        payload = results or (
            ToolResult(
                success=True,
                data={
                    "work_order_id": "WO-123",
                    "status": "open",
                    "issue_type": "plumbing",
                },
            ),
        )
        delayed = DelayedScriptedTool(payload, case.tool_delay_seconds)
        return {delayed.name: delayed}
    if results is not None:
        scripted = ScriptedTool(results)
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
    llm = _llm_for_case(case)
    model_timeout = (
        timeout if case.model_timeout_seconds is None else case.model_timeout_seconds
    )
    if case.router_kind == "llm":
        router = LlmAgentRouter(
            llm,
            allowed_tools=frozenset(tools),
            timeout_seconds=model_timeout,
        )
    else:
        router = AgentRouter()
    return AsyncAgentRuntime(
        llm,
        timeout_seconds=timeout,
        model_timeout_seconds=case.model_timeout_seconds,
        tool_timeout_seconds=case.tool_timeout_seconds,
        router=router,
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
        event_names=names_of(state.events),
    )


async def run_case(
    case: EvaluationCase,
    runtime: AsyncAgentRuntime | None = None,
) -> EvaluationResult:
    agent = runtime or _runtime_for_case(case)
    try:
        _answer, state = await agent.run_detailed(case.message)
    except DatabaseError:
        raise
    except AgentFailure as exc:
        if not isinstance(exc.state, AgentState):
            raise
        state = exc.state
    return EvaluationResult(
        case_name=case.name,
        expected=case.expected,
        actual=trajectory_from_state(state),
    )
