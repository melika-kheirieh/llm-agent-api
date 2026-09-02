import asyncio

import pytest

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.contracts import AgentAction, AgentRequest
from app.agent.llm_router import (
    ROUTING_PROMPT_MARKER,
    LlmAgentRouter,
    parse_routing_decision,
)
from app.agent.router import AgentRouter
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.infra.container import build_runtime
from app.infra.errors import FailureClass, RoutingError
from app.observability.events import TraceEventName
from app.observability.trace import trace_from_state


class RoutingFakeLLM:
    def __init__(self, route: str, answer: str = "from llm"):
        self.route = route
        self.answer = answer
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if ROUTING_PROMPT_MARKER in prompt:
            return self.route
        return self.answer


class RecordingTool:
    name = "work_order_lookup"

    def __init__(self, result: ToolResult):
        self.result = result
        self.calls: list[dict] = []

    async def execute(self, arguments: dict) -> ToolResult:
        self.calls.append(arguments)
        return self.result


def _success_tool() -> RecordingTool:
    return RecordingTool(
        ToolResult(
            success=True,
            data={
                "work_order_id": "WO-123",
                "status": "open",
                "issue_type": "plumbing",
            },
        )
    )


def test_parse_direct_decision():
    decision = parse_routing_decision(
        '{"action": "direct", "tool_name": null, "arguments": null}'
    )

    assert decision.action == AgentAction.DIRECT
    assert decision.tool_name is None
    assert decision.arguments is None


def test_parse_work_order_lookup_decision():
    decision = parse_routing_decision(
        '{"action": "use_tool", "tool_name": "work_order_lookup", '
        '"arguments": {"work_order_id": "WO-123"}}'
    )

    assert decision.action == AgentAction.USE_TOOL
    assert decision.tool_name == "work_order_lookup"
    assert decision.arguments == {"work_order_id": "WO-123"}


def test_parse_accepts_fenced_json():
    decision = parse_routing_decision(
        '```json\n{"action": "direct"}\n```'
    )

    assert decision.action == AgentAction.DIRECT


def test_parse_malformed_output_is_routing_error():
    with pytest.raises(RoutingError, match="Malformed routing output") as exc:
        parse_routing_decision("not json")

    assert exc.value.failure_class == FailureClass.MODEL_ERROR
    assert exc.value.decision is None


def test_parse_rejects_unknown_tool():
    with pytest.raises(RoutingError, match="Invalid tool selection") as exc:
        parse_routing_decision(
            '{"action": "use_tool", "tool_name": "billing_lookup", "arguments": {}}'
        )

    assert exc.value.decision.action == AgentAction.USE_TOOL
    assert exc.value.decision.tool_name == "billing_lookup"
    assert exc.value.decision.arguments == {}


def test_parse_rejects_non_string_work_order_id():
    with pytest.raises(RoutingError, match="Invalid routing arguments") as exc:
        parse_routing_decision(
            '{"action": "use_tool", "tool_name": "work_order_lookup", '
            '"arguments": {"work_order_id": 123}}'
        )

    assert exc.value.decision.arguments == {"work_order_id": 123}


def test_keyword_router_remains_available():
    decision = AgentRouter().decide(
        AgentRequest(message="Check work order WO-99", metadata={})
    )

    assert decision.action == AgentAction.USE_TOOL
    assert decision.tool_name == "work_order_lookup"
    assert decision.arguments == {"work_order_id": "WO-99"}


def test_build_runtime_uses_keyword_router():
    runtime = build_runtime(llm=RoutingFakeLLM("{}"))

    assert isinstance(runtime.router, AgentRouter)


def test_llm_router_direct_ignores_work_order_keywords():
    llm = RoutingFakeLLM('{"action": "direct"}')
    tool = _success_tool()
    runtime = AsyncAgentRuntime(
        llm,
        router=LlmAgentRouter(llm),
        tools={tool.name: tool},
        verifier=ToolVerifier(),
    )

    result = asyncio.run(runtime.run("Check work order WO-123"))

    assert result == "from llm"
    assert tool.calls == []
    assert any(ROUTING_PROMPT_MARKER in prompt for prompt in llm.prompts)


def test_llm_router_can_select_work_order_lookup():
    llm = RoutingFakeLLM(
        '{"action": "use_tool", "tool_name": "work_order_lookup", '
        '"arguments": {"work_order_id": "WO-123"}}'
    )
    tool = _success_tool()
    runtime = AsyncAgentRuntime(
        llm,
        router=LlmAgentRouter(llm),
        tools={tool.name: tool},
        verifier=ToolVerifier(),
    )

    result = asyncio.run(runtime.run("hello there"))

    assert result == "Work order WO-123 is open (plumbing)."
    assert tool.calls == [{"work_order_id": "WO-123"}]
    assert llm.prompts == [prompt for prompt in llm.prompts if ROUTING_PROMPT_MARKER in prompt]


def test_malformed_llm_routing_is_model_error():
    llm = RoutingFakeLLM("not a routing object")
    runtime = AsyncAgentRuntime(llm, router=LlmAgentRouter(llm))

    try:
        asyncio.run(runtime.run("hello there"))
        raise AssertionError("expected RoutingError")
    except RoutingError as exc:
        assert exc.failure_class == FailureClass.MODEL_ERROR
        assert isinstance(exc.state, AgentState)
        assert exc.state.status == AgentStatus.FAILED
        assert exc.state.decision is None
        names = tuple(event.name for event in exc.state.events)
        assert names == (
            TraceEventName.RUN_STARTED.value,
            TraceEventName.RUN_FAILED.value,
        )
        trace = trace_from_state(exc.state)
        assert trace.outcome == "failure"
        assert trace.failure_class == FailureClass.MODEL_ERROR.value
