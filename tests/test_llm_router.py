import asyncio

import pytest

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.contracts import AgentAction, AgentRequest
from app.agent.llm_router import (
    ROUTING_PROMPT_MARKER,
    LlmAgentRouter,
    decision_from_routing_output,
)
from app.agent.router import AgentRouter
from app.agent.schemas import RoutingOutput
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.infra.config import ROUTER_MODE_KEYWORD, settings
from app.infra.container import build_runtime
from app.infra.errors import FailureClass, ModelError, RoutingError
from app.observability.events import TraceEventName
from app.observability.trace import trace_from_state
from app.tools.catalog import DEFAULT_SCOPE, scoped_work_order_data


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


class TypedRoutingLLM:
    def __init__(self, output: RoutingOutput, answer: str = "from llm"):
        self.output = output
        self.answer = answer
        self.structured_prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        return self.answer

    async def generate_structured(self, prompt: str, schema):
        self.structured_prompts.append(prompt)
        return schema.model_validate(self.output.model_dump())


class FailingStructuredLLM:
    async def generate(self, prompt: str) -> str:
        return "unused"

    async def generate_structured(self, prompt: str, schema):
        raise ModelError("provider down")


class RecordingTool:
    name = "work_order_lookup"

    def __init__(self, result: ToolResult):
        self.result = result
        self.calls: list[dict] = []

    async def execute(self, arguments: dict, *, trusted_scope=None) -> ToolResult:
        self.calls.append(arguments)
        return self.result


def _success_tool() -> RecordingTool:
    return RecordingTool(
        ToolResult(
            success=True,
            data=scoped_work_order_data(),
        )
    )


def test_decision_from_direct_output():
    decision = decision_from_routing_output(
        RoutingOutput(action=AgentAction.DIRECT, tool_name=None, arguments=None)
    )

    assert decision.action == AgentAction.DIRECT
    assert decision.tool_name is None
    assert decision.arguments is None


def test_decision_from_work_order_lookup_output():
    decision = decision_from_routing_output(
        RoutingOutput(
            action=AgentAction.USE_TOOL,
            tool_name="work_order_lookup",
            arguments={"work_order_id": "WO-123"},
        )
    )

    assert decision.action == AgentAction.USE_TOOL
    assert decision.tool_name == "work_order_lookup"
    assert decision.arguments == {"work_order_id": "WO-123"}


def test_decision_rejects_unknown_tool():
    with pytest.raises(RoutingError, match="Invalid tool selection") as exc:
        decision_from_routing_output(
            RoutingOutput(
                action=AgentAction.USE_TOOL,
                tool_name="billing_lookup",
                arguments={},
            )
        )

    assert exc.value.decision.action == AgentAction.USE_TOOL
    assert exc.value.decision.tool_name == "billing_lookup"
    assert exc.value.decision.arguments == {}


def test_decision_rejects_scope_fields_in_tool_arguments():
    with pytest.raises(RoutingError, match="Invalid routing arguments"):
        decision_from_routing_output(
            RoutingOutput(
                action=AgentAction.USE_TOOL,
                tool_name="work_order_lookup",
                arguments={"work_order_id": "WO-123", "tenant_id": "tenant-a"},
            )
        )


def test_decision_from_policy_lookup_output():
    decision = decision_from_routing_output(
        RoutingOutput(
            action=AgentAction.USE_TOOL,
            tool_name="maintenance_policy_lookup",
            arguments={"issue_type": "plumbing"},
        )
    )

    assert decision.tool_name == "maintenance_policy_lookup"
    assert decision.arguments == {"issue_type": "plumbing"}


def test_decision_rejects_non_string_work_order_id():
    with pytest.raises(RoutingError, match="Invalid routing arguments") as exc:
        decision_from_routing_output(
            RoutingOutput(
                action=AgentAction.USE_TOOL,
                tool_name="work_order_lookup",
                arguments={"work_order_id": 123},
            )
        )

    assert exc.value.decision.arguments == {"work_order_id": 123}


def test_keyword_router_remains_available():
    decision = AgentRouter().decide(
        AgentRequest(message="Check work order WO-99", metadata={})
    )

    assert decision.action == AgentAction.USE_TOOL
    assert decision.tool_name == "work_order_lookup"
    assert decision.arguments == {"work_order_id": "WO-99"}


def test_build_runtime_uses_keyword_router(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", ROUTER_MODE_KEYWORD)
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


def test_llm_router_uses_typed_provider_decision():
    llm = TypedRoutingLLM(RoutingOutput(action=AgentAction.DIRECT))
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
    assert llm.structured_prompts
    assert ROUTING_PROMPT_MARKER in llm.structured_prompts[0]


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

    result = asyncio.run(
        runtime.run("hello there", trusted_scope=DEFAULT_SCOPE)
    )

    assert result == "Work order WO-123 is open (plumbing)."
    assert tool.calls == [{"work_order_id": "WO-123"}]
    assert llm.prompts == [
        prompt for prompt in llm.prompts if ROUTING_PROMPT_MARKER in prompt
    ]


def test_malformed_llm_routing_is_model_error():
    llm = RoutingFakeLLM("not a routing object")
    runtime = AsyncAgentRuntime(llm, router=LlmAgentRouter(llm))

    try:
        asyncio.run(runtime.run("hello there"))
        raise AssertionError("expected ModelError")
    except ModelError as exc:
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


def test_schema_invalid_routing_is_model_error_not_routing_error():
    llm = RoutingFakeLLM('{"action": "direct", "unexpected": true}')
    runtime = AsyncAgentRuntime(llm, router=LlmAgentRouter(llm))

    try:
        asyncio.run(runtime.run("hello there"))
        raise AssertionError("expected ModelError")
    except ModelError as exc:
        assert not isinstance(exc, RoutingError)
        assert exc.failure_class == FailureClass.MODEL_ERROR
        assert isinstance(exc.state, AgentState)
        assert exc.state.decision is None


def test_structured_provider_failure_is_model_error():
    llm = FailingStructuredLLM()
    runtime = AsyncAgentRuntime(llm, router=LlmAgentRouter(llm))

    try:
        asyncio.run(runtime.run("hello there"))
        raise AssertionError("expected ModelError")
    except ModelError as exc:
        assert "provider down" in str(exc)
        assert exc.failure_class == FailureClass.MODEL_ERROR
        assert isinstance(exc.state, AgentState)
        assert exc.state.decision is None
