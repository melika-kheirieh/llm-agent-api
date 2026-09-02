import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.router import AgentRouter
from app.agent.state import AgentStatus
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.evaluation.agent_cases import (
    DIRECT_SUCCESS_EVENTS,
    MODEL_FAILURE_EVENTS,
    RETRY_THEN_SUCCESS_EVENTS,
    TOOL_FAILURE_EVENTS,
    TOOL_SUCCESS_EVENTS,
)
from app.observability.events import TraceEventName
from app.observability.trace import ExecutionTrace
from app.tools.catalog import DEFAULT_SCOPE, scoped_work_order_data


class FakeLLM:
    async def generate(self, prompt: str) -> str:
        return "direct answer"


class RecordingTool:
    name = "work_order_lookup"

    def __init__(self, result: ToolResult | list[ToolResult]):
        self.results = [result] if isinstance(result, ToolResult) else list(result)
        self.calls: list[dict] = []

    async def execute(self, arguments: dict, *, trusted_scope=None) -> ToolResult:
        self.calls.append(arguments)
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[index]


def _event_names(trace: ExecutionTrace) -> tuple[str, ...]:
    return tuple(event.name for event in trace.events)


def test_direct_run_emits_expected_events():
    runtime = _runtime()
    _answer, trace = asyncio.run(runtime.run_with_trace("hello there"))

    assert _event_names(trace) == DIRECT_SUCCESS_EVENTS
    assert [event.order for event in trace.events] == list(range(len(trace.events)))
    assert TraceEventName.RUN_COMPLETED.value in _event_names(trace)
    assert "event_names" in trace.as_log_fields()
    assert trace.as_log_fields()["event_names"] == list(DIRECT_SUCCESS_EVENTS)
    assert trace.as_log_fields()["router_type"] == "keyword"
    assert trace.as_log_fields()["decision"] == "direct"
    assert trace.as_log_fields()["selected_tool"] is None
    assert isinstance(trace.as_log_fields()["routing_ms"], float)
    assert trace.as_log_fields()["routing_ms"] >= 0


def test_successful_tool_run_emits_expected_events():
    tool = RecordingTool(
        ToolResult(
            success=True,
            data=scoped_work_order_data(),
        )
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(
        runtime.run_with_trace("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    assert _event_names(trace) == TOOL_SUCCESS_EVENTS
    assert trace.events[2].metadata["attempt"] == 1
    assert trace.error_code is None
    assert trace.as_log_fields()["error_code"] is None


def test_scope_rejection_log_fields_use_error_code_not_scope():
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "cross_tenant"}, retryable=False)
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(
        runtime.run_with_trace("Check work order WO-999", trusted_scope=DEFAULT_SCOPE)
    )

    fields = trace.as_log_fields()
    assert _event_names(trace) == TOOL_FAILURE_EVENTS
    assert fields["failure_class"] == "tool_error"
    assert fields["error_code"] == "cross_tenant"
    assert "tenant_id" not in fields
    assert "property_id" not in fields
    failed = next(
        event for event in trace.events if event.name == TraceEventName.TOOL_FAILED.value
    )
    assert failed.metadata["error"] == "cross_tenant"
    assert "tenant_id" not in failed.metadata
    assert "property_id" not in failed.metadata


def test_retry_flow_contains_recovery_retry_event():
    tool = RecordingTool(
        [
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(
                success=True,
                data=scoped_work_order_data(),
            ),
        ]
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(
        runtime.run_with_trace("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    names = _event_names(trace)
    assert names == RETRY_THEN_SUCCESS_EVENTS
    assert TraceEventName.RECOVERY_DECISION.value in names
    recovery = next(
        event for event in trace.events if event.name == TraceEventName.RECOVERY_DECISION.value
    )
    assert recovery.metadata["action"] == "retry"
    assert trace.error_code is None


def test_failure_flow_contains_run_failed_event():
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "missing_work_order_id"})
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(runtime.run_with_trace("Need maintenance help"))

    names = _event_names(trace)
    assert names == TOOL_FAILURE_EVENTS
    assert TraceEventName.RUN_FAILED.value in names
    assert TraceEventName.RUN_COMPLETED.value not in names


def test_model_timeout_emits_run_failed():
    from app.infra.errors import ModelTimeout

    class SlowLLM:
        async def generate(self, prompt: str) -> str:
            await asyncio.sleep(1.0)
            return "unreachable"

    runtime = AsyncAgentRuntime(SlowLLM(), model_timeout_seconds=0.05)
    try:
        asyncio.run(runtime.run_with_trace("hello there"))
        raise AssertionError("expected ModelTimeout")
    except ModelTimeout as exc:
        from app.observability.trace import trace_from_state

        assert exc.state is not None
        trace = trace_from_state(exc.state)
        assert _event_names(trace) == MODEL_FAILURE_EVENTS


def _runtime(tool: RecordingTool | None = None) -> AsyncAgentRuntime:
    tools = {tool.name: tool} if tool is not None else {}
    return AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools=tools,
        verifier=ToolVerifier(),
    )


def test_direct_run_creates_completed_trace():
    runtime = _runtime()
    answer, trace = asyncio.run(runtime.run_with_trace("hello there"))

    assert answer == "direct answer"
    assert isinstance(trace, ExecutionTrace)
    assert trace.terminal_status == AgentStatus.COMPLETED.value
    assert trace.decision == "direct"
    assert trace.selected_tool is None
    assert trace.verification_result is None
    assert trace.attempts == 0
    assert trace.retry_count == 0
    assert trace.outcome == "success"
    assert trace.recovery_decision is None
    assert trace.router_type == "keyword"
    assert trace.run_id


def test_successful_tool_run_includes_tool_and_verification():
    tool = RecordingTool(
        ToolResult(
            success=True,
            data=scoped_work_order_data(),
        )
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(
        runtime.run_with_trace("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    assert trace.terminal_status == AgentStatus.COMPLETED.value
    assert trace.decision == "use_tool"
    assert trace.selected_tool == "work_order_lookup"
    assert trace.verification_result == "true"
    assert trace.attempts == 1
    assert trace.retry_count == 0
    assert trace.outcome == "success"


def test_verification_failure_trace_has_review_status():
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "missing_work_order_id"})
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(runtime.run_with_trace("Need maintenance help"))

    assert trace.terminal_status == AgentStatus.NEEDS_HUMAN_REVIEW.value
    assert trace.decision == "use_tool"
    assert trace.selected_tool == "work_order_lookup"
    assert trace.verification_result == "false"
    assert trace.attempts == 1
    assert trace.retry_count == 0
    assert trace.outcome == "needs_human_review"
    assert trace.failure_class == "tool_error"


def test_retry_path_reports_attempt_count():
    tool = RecordingTool(
        [
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(
                success=True,
                data=scoped_work_order_data(),
            ),
        ]
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(
        runtime.run_with_trace("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    assert len(tool.calls) == 2
    assert trace.terminal_status == AgentStatus.COMPLETED.value
    assert trace.attempts == 2
    assert trace.retry_count == 1
    assert trace.verification_result == "true"
    assert trace.outcome == "success"
    assert trace.recovery_decision == "retry"


def test_llm_router_trace_exposes_router_type_and_timing():
    from app.agent.llm_router import ROUTING_PROMPT_MARKER, LlmAgentRouter

    class RoutingFakeLLM:
        async def generate(self, prompt: str) -> str:
            if ROUTING_PROMPT_MARKER in prompt:
                return '{"action": "direct"}'
            return "direct answer"

    llm = RoutingFakeLLM()
    runtime = AsyncAgentRuntime(llm, router=LlmAgentRouter(llm))
    _answer, trace = asyncio.run(
        runtime.run_with_trace("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    fields = trace.as_log_fields()
    assert trace.router_type == "llm"
    assert fields["router_type"] == "llm"
    assert fields["decision"] == "direct"
    assert fields["selected_tool"] is None
    assert isinstance(fields["routing_ms"], float)
    assert fields["routing_ms"] >= 0
    route_event = next(
        event for event in trace.events if event.name == TraceEventName.ROUTE_SELECTED.value
    )
    assert route_event.metadata["router_type"] == "llm"
    assert route_event.metadata["action"] == "direct"
