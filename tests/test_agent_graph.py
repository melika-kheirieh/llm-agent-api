import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.router import AgentRouter
from app.agent.state import AgentStatus
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.evaluation.agent_cases import (
    DIRECT_SUCCESS_EVENTS,
    RETRY_THEN_SUCCESS_EVENTS,
    TOOL_FAILURE_EVENTS,
    TOOL_SUCCESS_EVENTS,
)
from app.infra.errors import FailureClass
from app.observability.events import event_names


class FakeLLM:
    def __init__(self, text: str = "generated answer"):
        self.text = text
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.text


class RecordingTool:
    name = "work_order_lookup"

    def __init__(self, result: ToolResult | list[ToolResult]):
        self.results = [result] if isinstance(result, ToolResult) else list(result)
        self.calls: list[dict] = []

    async def execute(self, arguments: dict) -> ToolResult:
        self.calls.append(arguments)
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[index]


def _runtime(llm: FakeLLM, tool: RecordingTool | None = None) -> AsyncAgentRuntime:
    tools = {tool.name: tool} if tool is not None else {}
    return AsyncAgentRuntime(
        llm,
        router=AgentRouter(),
        tools=tools,
        verifier=ToolVerifier(),
    )


def _valid_result(work_order_id: str = "WO-123") -> ToolResult:
    return ToolResult(
        success=True,
        data={
            "work_order_id": work_order_id,
            "status": "open",
            "issue_type": "plumbing",
        },
    )


def test_direct_path_returns_llm_answer_without_tools():
    llm = FakeLLM("  from llm  ")
    tool = RecordingTool(_valid_result())
    runtime = _runtime(llm, tool)

    answer, state = asyncio.run(runtime.run_detailed("hello there"))

    assert answer == "from llm"
    assert llm.prompts == ["Answer clearly.\n\nUser: hello there"]
    assert tool.calls == []
    assert state.status == AgentStatus.COMPLETED
    assert event_names(state.events) == DIRECT_SUCCESS_EVENTS


def test_tool_success_path_skips_llm():
    llm = FakeLLM("should not be used")
    tool = RecordingTool(_valid_result())
    runtime = _runtime(llm, tool)

    answer, state = asyncio.run(runtime.run_detailed("Check work order WO-123"))

    assert answer == "Work order WO-123 is open (plumbing)."
    assert llm.prompts == []
    assert tool.calls == [{"work_order_id": "WO-123"}]
    assert state.verification_result is True
    assert state.status == AgentStatus.COMPLETED
    assert event_names(state.events) == TOOL_SUCCESS_EVENTS


def test_verification_failure_path_goes_to_review():
    llm = FakeLLM("should not be used")
    tool = RecordingTool(
        ToolResult(
            success=True,
            data={
                "work_order_id": "WO-123",
                "status": "lost",
                "issue_type": "plumbing",
            },
        )
    )
    runtime = _runtime(llm, tool)

    answer, state = asyncio.run(runtime.run_detailed("Check work order WO-123"))

    assert answer == "The request could not be verified."
    assert llm.prompts == []
    assert len(tool.calls) == 1
    assert state.verification_result is False
    assert state.failure_class == FailureClass.VERIFICATION_FAILURE
    assert state.status == AgentStatus.NEEDS_HUMAN_REVIEW
    assert state.recovery_decision.value == "fail"
    assert event_names(state.events) == (
        "run_started",
        "route_selected",
        "tool_started",
        "tool_completed",
        "verification_completed",
        "recovery_decision",
        "run_failed",
    )


def test_retry_path_succeeds_on_second_attempt():
    llm = FakeLLM("should not be used")
    tool = RecordingTool(
        [
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            _valid_result(),
        ]
    )
    runtime = _runtime(llm, tool)

    answer, state = asyncio.run(runtime.run_detailed("Check work order WO-123"))

    assert answer == "Work order WO-123 is open (plumbing)."
    assert llm.prompts == []
    assert len(tool.calls) == 2
    assert state.attempts == 2
    assert state.verification_result is True
    assert state.recovery_decision.value == "retry"
    assert state.status == AgentStatus.COMPLETED
    assert event_names(state.events) == RETRY_THEN_SUCCESS_EVENTS


def test_terminal_failure_path_stops_after_recovery():
    llm = FakeLLM("should not be used")
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "not_found"}, retryable=False)
    )
    runtime = _runtime(llm, tool)

    answer, state = asyncio.run(runtime.run_detailed("Check work order WO-123"))

    assert answer == "The request could not be verified."
    assert llm.prompts == []
    assert len(tool.calls) == 1
    assert state.attempts == 1
    assert state.verification_result is False
    assert state.failure_class == FailureClass.TOOL_ERROR
    assert state.recovery_decision.value == "fail"
    assert state.status == AgentStatus.NEEDS_HUMAN_REVIEW
    assert event_names(state.events) == TOOL_FAILURE_EVENTS
