import asyncio
from dataclasses import replace

from app.agent.context import ContextItem, ContextPolicy
from app.agent.contracts import AgentAction, AgentDecision, AgentRequest
from app.agent.observation import Observation
from app.agent.recovery import RecoveryAction, RecoveryPolicy
from app.agent.router import AgentRouter, Router
from app.agent.schemas import Analysis
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import AgentTool, ToolResult
from app.agent.verification import ToolVerifier
from app.infra.errors import (
    AgentFailure,
    FailureClass,
    ModelTimeout,
    UnknownFailure,
)
from app.llm.async_base import AsyncLLMClient
from app.observability.events import TraceEventName
from app.observability.trace import ExecutionTrace, trace_from_state
from app.tools.work_order import WorkOrderObservation

_REVIEW_RESPONSE = "The request could not be verified."


class AsyncAgentRuntime:
    """Async execution boundary for the chat agent pipeline."""

    def __init__(
        self,
        llm: AsyncLLMClient,
        timeout_seconds: float = 60.0,
        model_timeout_seconds: float | None = None,
        tool_timeout_seconds: float | None = None,
        router: Router | None = None,
        tools: dict[str, AgentTool] | None = None,
        verifier: ToolVerifier | None = None,
        recovery: RecoveryPolicy | None = None,
        context_policy: ContextPolicy | None = None,
    ):
        self.llm = llm
        self.timeout_seconds = timeout_seconds
        self.model_timeout_seconds = (
            timeout_seconds if model_timeout_seconds is None else model_timeout_seconds
        )
        self.tool_timeout_seconds = (
            timeout_seconds if tool_timeout_seconds is None else tool_timeout_seconds
        )
        self.router = router or AgentRouter()
        self.tools = tools or {}
        self.verifier = verifier or ToolVerifier()
        self.recovery = recovery or RecoveryPolicy(max_attempts=2)
        self.context_policy = context_policy or ContextPolicy()

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    async def respond(self, message: str, analysis: Analysis) -> str:
        prompt = f"Answer clearly.\n\nUser: {message}"
        try:
            async with asyncio.timeout(self.model_timeout_seconds):
                return (await self.llm.generate(prompt)).strip()
        except asyncio.CancelledError:
            raise
        except TimeoutError as e:
            raise ModelTimeout("Model request timed out") from e

    async def run(self, message: str) -> str:
        answer, _state = await self.run_detailed(message)
        return answer

    async def run_with_trace(self, message: str) -> tuple[str, ExecutionTrace]:
        answer, state = await self.run_detailed(message)
        return answer, trace_from_state(state)

    async def run_detailed(self, message: str) -> tuple[str, AgentState]:
        try:
            return await self._execute(message)
        except asyncio.CancelledError:
            raise
        except AgentFailure:
            raise
        except Exception as e:
            raise UnknownFailure(str(e)) from e

    async def _execute(self, message: str) -> tuple[str, AgentState]:
        request = AgentRequest(message=message, metadata={})
        state = AgentState(request=request, status=AgentStatus.RUNNING)
        state = state.record(TraceEventName.RUN_STARTED)
        try:
            decision = await self.router.route(request)
        except AgentFailure as exc:
            decision = getattr(exc, "decision", None)
            if decision is not None:
                state = replace(state, decision=decision)
                state = state.record(
                    TraceEventName.ROUTE_SELECTED,
                    action=decision.action.value,
                    tool_name=decision.tool_name,
                )
            state = replace(
                state,
                status=AgentStatus.FAILED,
                failure_class=exc.failure_class,
            )
            state = state.record(
                TraceEventName.RUN_FAILED,
                status=AgentStatus.FAILED.value,
                failure_class=exc.failure_class.value,
            )
            exc.state = state
            raise
        state = replace(state, decision=decision)
        state = state.record(
            TraceEventName.ROUTE_SELECTED,
            action=decision.action.value,
            tool_name=decision.tool_name,
        )

        if decision.action == AgentAction.DIRECT:
            analysis = self.analyze(message)
            try:
                answer = await self.respond(message, analysis)
            except AgentFailure as exc:
                state = state.record(
                    TraceEventName.RUN_FAILED,
                    status=AgentStatus.FAILED.value,
                    failure_class=exc.failure_class.value,
                )
                exc.state = replace(
                    state,
                    status=AgentStatus.FAILED,
                    failure_class=exc.failure_class,
                )
                raise
            state = replace(state, status=AgentStatus.COMPLETED)
            state = state.record(
                TraceEventName.RUN_COMPLETED,
                status=AgentStatus.COMPLETED.value,
            )
            return answer, state

        if decision.action == AgentAction.USE_TOOL:
            return await self._run_tool(state, decision)

        state = replace(
            state,
            status=AgentStatus.NEEDS_HUMAN_REVIEW,
            failure_class=FailureClass.UNKNOWN,
        )
        state = state.record(
            TraceEventName.RUN_FAILED,
            status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
            failure_class=FailureClass.UNKNOWN.value,
        )
        return _REVIEW_RESPONSE, state

    async def _run_tool(
        self, state: AgentState, decision: AgentDecision
    ) -> tuple[str, AgentState]:
        tool = self.tools.get(decision.tool_name or "")
        if tool is None:
            state = replace(
                state,
                status=AgentStatus.NEEDS_HUMAN_REVIEW,
                failure_class=FailureClass.TOOL_ERROR,
            )
            state = state.record(
                TraceEventName.RUN_FAILED,
                status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
                failure_class=FailureClass.TOOL_ERROR.value,
            )
            return _REVIEW_RESPONSE, state

        while True:
            arguments = decision.arguments or {}
            attempt = state.attempts + 1
            attempt_class: FailureClass | None = None
            state = state.record(
                TraceEventName.TOOL_STARTED,
                tool_name=tool.name,
                attempt=attempt,
            )
            try:
                async with asyncio.timeout(self.tool_timeout_seconds):
                    result = await tool.execute(arguments)
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                result = ToolResult(
                    success=False,
                    data={"error": "tool_timeout"},
                    retryable=True,
                )
                attempt_class = FailureClass.TOOL_TIMEOUT
            except Exception:
                result = ToolResult(
                    success=False,
                    data={"error": "tool_error"},
                    retryable=False,
                )
                attempt_class = FailureClass.TOOL_ERROR

            if result.success:
                state = state.record(
                    TraceEventName.TOOL_COMPLETED,
                    tool_name=tool.name,
                    attempt=attempt,
                )
            else:
                failed_class = (
                    attempt_class.value
                    if attempt_class is not None
                    else FailureClass.TOOL_ERROR.value
                )
                state = state.record(
                    TraceEventName.TOOL_FAILED,
                    tool_name=tool.name,
                    attempt=attempt,
                    failure_class=failed_class,
                )

            observation = Observation(
                tool_name=tool.name,
                success=result.success,
                data=result.data,
            )
            selected = self.context_policy.select(
                [ContextItem(key="tool_observation", value=observation, source="tool")]
            )
            verified = self.verifier.verify(result, arguments)
            state = state.record(
                TraceEventName.VERIFICATION_COMPLETED,
                verified=verified,
            )
            if verified:
                failure_class = None
            elif attempt_class is not None:
                failure_class = attempt_class
            elif not result.success:
                failure_class = FailureClass.TOOL_ERROR
            else:
                failure_class = FailureClass.VERIFICATION_FAILURE

            state = replace(
                state,
                attempts=attempt,
                tool_result=result,
                verification_result=verified,
                observations=state.observations + (observation,),
                failure_class=failure_class,
                status=(
                    AgentStatus.COMPLETED if verified else AgentStatus.RUNNING
                ),
            )
            if verified:
                last = selected[-1].value if selected else observation
                state = state.record(
                    TraceEventName.RUN_COMPLETED,
                    status=AgentStatus.COMPLETED.value,
                )
                return _format_tool_answer(last), state

            action = self.recovery.decide(attempt, result.retryable)
            state = replace(state, recovery_decision=action)
            state = state.record(
                TraceEventName.RECOVERY_DECISION,
                action=action.value,
            )
            if action == RecoveryAction.RETRY:
                continue

            state = replace(state, status=AgentStatus.NEEDS_HUMAN_REVIEW)
            state = state.record(
                TraceEventName.RUN_FAILED,
                status=AgentStatus.NEEDS_HUMAN_REVIEW.value,
                failure_class=failure_class.value if failure_class is not None else None,
            )
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
