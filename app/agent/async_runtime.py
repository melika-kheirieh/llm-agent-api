import asyncio
from dataclasses import replace

from app.agent.context import ContextItem, ContextPolicy
from app.agent.contracts import AgentAction, AgentDecision, AgentRequest
from app.agent.observation import Observation
from app.agent.recovery import RecoveryAction, RecoveryPolicy
from app.agent.router import AgentRouter
from app.agent.schemas import Analysis
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import AgentTool
from app.agent.verification import ToolVerifier
from app.infra.errors import UpstreamLLMError
from app.llm.async_base import AsyncLLMClient
from app.observability.trace import ExecutionTrace, trace_from_state
from app.tools.work_order import WorkOrderObservation

_REVIEW_RESPONSE = "The request could not be verified."


class AsyncAgentRuntime:
    """Async execution boundary for the chat agent pipeline."""

    def __init__(
        self,
        llm: AsyncLLMClient,
        timeout_seconds: float = 60.0,
        router: AgentRouter | None = None,
        tools: dict[str, AgentTool] | None = None,
        verifier: ToolVerifier | None = None,
        recovery: RecoveryPolicy | None = None,
        context_policy: ContextPolicy | None = None,
    ):
        self.llm = llm
        self.timeout_seconds = timeout_seconds
        self.router = router or AgentRouter()
        self.tools = tools or {}
        self.verifier = verifier or ToolVerifier()
        self.recovery = recovery or RecoveryPolicy(max_attempts=2)
        self.context_policy = context_policy or ContextPolicy()

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    async def respond(self, message: str, analysis: Analysis) -> str:
        prompt = f"Answer clearly.\n\nUser: {message}"
        return (await self.llm.generate(prompt)).strip()

    async def run(self, message: str) -> str:
        answer, _state = await self.run_detailed(message)
        return answer

    async def run_with_trace(self, message: str) -> tuple[str, ExecutionTrace]:
        answer, state = await self.run_detailed(message)
        return answer, trace_from_state(state)

    async def run_detailed(self, message: str) -> tuple[str, AgentState]:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._execute(message)
        except TimeoutError as e:
            raise UpstreamLLMError("LLM request timed out") from e

    async def _execute(self, message: str) -> tuple[str, AgentState]:
        request = AgentRequest(message=message, metadata={})
        state = AgentState(request=request, status=AgentStatus.RUNNING)
        decision = self.router.route(request)
        state = replace(state, decision=decision)

        if decision.action == AgentAction.DIRECT:
            analysis = self.analyze(message)
            answer = await self.respond(message, analysis)
            state = replace(state, status=AgentStatus.COMPLETED)
            return answer, state

        if decision.action == AgentAction.USE_TOOL:
            return await self._run_tool(state, decision)

        state = replace(state, status=AgentStatus.NEEDS_HUMAN_REVIEW)
        return _REVIEW_RESPONSE, state

    async def _run_tool(
        self, state: AgentState, decision: AgentDecision
    ) -> tuple[str, AgentState]:
        tool = self.tools.get(decision.tool_name or "")
        if tool is None:
            state = replace(state, status=AgentStatus.NEEDS_HUMAN_REVIEW)
            return _REVIEW_RESPONSE, state

        while True:
            result = await tool.execute(decision.arguments or {})
            observation = Observation(
                tool_name=tool.name,
                success=result.success,
                data=result.data,
            )
            selected = self.context_policy.select(
                [ContextItem(key="tool_observation", value=observation, source="tool")]
            )
            verified = self.verifier.verify(result, decision.arguments or {})
            attempts = state.attempts + 1
            state = replace(
                state,
                attempts=attempts,
                tool_result=result,
                verification_result=verified,
                observations=state.observations + (observation,),
                status=(
                    AgentStatus.COMPLETED if verified else AgentStatus.RUNNING
                ),
            )
            if verified:
                last = selected[-1].value if selected else observation
                return _format_tool_answer(last), state

            action = self.recovery.decide(attempts, result.retryable)
            if action == RecoveryAction.RETRY:
                continue

            state = replace(state, status=AgentStatus.NEEDS_HUMAN_REVIEW)
            return _REVIEW_RESPONSE, state

    async def aclose(self) -> None:
        aclose = getattr(self.llm, "aclose", None)
        if aclose is not None:
            await aclose()


def _format_tool_answer(observation: Observation) -> str:
    parsed = WorkOrderObservation.from_data(observation.data)
    if parsed is None:
        return "Tool execution completed."
    issue = f" ({parsed.issue_type})" if parsed.issue_type else ""
    return f"Work order {parsed.work_order_id} is {parsed.status}{issue}."
