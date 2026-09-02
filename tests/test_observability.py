import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.router import AgentRouter
from app.agent.state import AgentStatus
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.observability.trace import ExecutionTrace


class FakeLLM:
    async def generate(self, prompt: str) -> str:
        return "direct answer"


class RecordingTool:
    name = "work_order_lookup"

    def __init__(self, result: ToolResult | list[ToolResult]):
        self.results = [result] if isinstance(result, ToolResult) else list(result)
        self.calls: list[dict] = []

    async def execute(self, arguments: dict) -> ToolResult:
        self.calls.append(arguments)
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[index]


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
    assert trace.run_id


def test_successful_tool_run_includes_tool_and_verification():
    tool = RecordingTool(
        ToolResult(
            success=True,
            data={"work_order_id": "WO-123", "status": "open", "issue_type": "plumbing"},
        )
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(runtime.run_with_trace("Check work order WO-123"))

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
                data={
                    "work_order_id": "WO-123",
                    "status": "open",
                    "issue_type": "plumbing",
                },
            ),
        ]
    )
    runtime = _runtime(tool)
    _answer, trace = asyncio.run(runtime.run_with_trace("Check work order WO-123"))

    assert len(tool.calls) == 2
    assert trace.terminal_status == AgentStatus.COMPLETED.value
    assert trace.attempts == 2
    assert trace.retry_count == 1
    assert trace.verification_result == "true"
    assert trace.outcome == "success"
