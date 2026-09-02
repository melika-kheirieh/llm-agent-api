import asyncio
from dataclasses import replace

from app.agent.context import (
    ContextPolicy,
    HistoryTurn,
    RequestContext,
    ThreadHistoryBuffer,
    TrustedScope,
    render_answer_prompt,
)
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
        self._history = ThreadHistoryBuffer()

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    async def respond(self, message: str, analysis: Analysis) -> str:
        return await self._respond_from_context(
            self.context_policy.assemble(
                RequestContext(message=message)
            ).answer,
            analysis,
        )

    async def _respond_from_context(
        self, answer_context, _analysis: Analysis
    ) -> str:
        prompt = render_answer_prompt(answer_context)
        try:
            async with asyncio.timeout(self.model_timeout_seconds):
                return (await self.llm.generate(prompt)).strip()
        except asyncio.CancelledError:
            raise
        except TimeoutError as e:
            raise ModelTimeout("Model request timed out") from e

    async def run(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        history: tuple[HistoryTurn, ...] | None = None,
        trusted_scope: TrustedScope | None = None,
    ) -> str:
        answer, _state = await self.run_detailed(
            message,
            thread_id=thread_id,
            history=history,
            trusted_scope=trusted_scope,
        )
        return answer

    async def run_with_trace(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        history: tuple[HistoryTurn, ...] | None = None,
        trusted_scope: TrustedScope | None = None,
    ) -> tuple[str, ExecutionTrace]:
        answer, state = await self.run_detailed(
            message,
            thread_id=thread_id,
            history=history,
            trusted_scope=trusted_scope,
        )
        return answer, trace_from_state(state)

    async def run_detailed(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        history: tuple[HistoryTurn, ...] | None = None,
        trusted_scope: TrustedScope | None = None,
    ) -> tuple[str, AgentState]:
        try:
            answer, state = await self._execute(
                message,
                thread_id=thread_id,
                history=history,
                trusted_scope=trusted_scope,
            )
        except asyncio.CancelledError:
            raise
        except AgentFailure:
            raise
        except Exception as e:
            raise UnknownFailure(str(e)) from e
        self._history.record(
            thread_id,
            message,
            answer,
            self.context_policy.max_history,
        )
        return answer, state

    async def _execute(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        history: tuple[HistoryTurn, ...] | None = None,
        trusted_scope: TrustedScope | None = None,
    ) -> tuple[str, AgentState]:
        scope = trusted_scope or TrustedScope()
        prior = self._history.turns(thread_id) if history is None else history
        request_ctx = RequestContext(
            message=message,
            thread_id=thread_id,
            history=prior,
            trusted_scope=scope,
        )
        agent_ctx = self.context_policy.assemble(request_ctx)
        request = AgentRequest(message=message, metadata={})
        router_type = getattr(self.router, "router_type", None)
        state = AgentState(
            request=request,
            context=agent_ctx,
            status=AgentStatus.RUNNING,
            router_type=router_type,
        )
        state = state.record(TraceEventName.RUN_STARTED, router_type=router_type)
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
                    router_type=router_type,
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
            router_type=router_type,
        )

        if decision.action == AgentAction.DIRECT:
            analysis = self.analyze(message)
            try:
                answer = await self._respond_from_context(
                    self.context_policy.for_answer(agent_ctx),
                    analysis,
                )
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
            return await self._run_tool(state, decision, request_ctx)

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
        self,
        state: AgentState,
        decision: AgentDecision,
        request_ctx: RequestContext,
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
            observations = state.observations + (observation,)
            verified = self.verifier.verify(result, arguments)
            agent_ctx = self.context_policy.assemble(
                request_ctx,
                observations=observations,
                verification_result=verified,
                attempts=attempt,
            )
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
                observations=observations,
                context=agent_ctx,
                failure_class=failure_class,
                status=(
                    AgentStatus.COMPLETED if verified else AgentStatus.RUNNING
                ),
            )
            if verified:
                last = observation
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
