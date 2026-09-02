import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.contracts import AgentAction, AgentRequest
from app.agent.router import AgentRouter
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.tools.work_order import WorkOrderLookupTool


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


def test_direct_path_calls_llm():
    llm = FakeLLM("  from llm  ")
    tool = RecordingTool(ToolResult(success=True, data={"work_order_id": "WO-1"}))
    runtime = _runtime(llm, tool)

    result = asyncio.run(runtime.run("hello there"))

    assert result == "from llm"
    assert llm.prompts == ["Answer clearly.\n\nUser: hello there"]
    assert tool.calls == []


def test_use_tool_path_executes_tool_and_verifier(mocker):
    llm = FakeLLM("should not be used")
    tool = RecordingTool(
        ToolResult(
            success=True,
            data={
                "work_order_id": "WO-123",
                "status": "open",
                "issue_type": "plumbing",
            },
        )
    )
    verifier = ToolVerifier()
    spy = mocker.spy(verifier, "verify")
    runtime = AsyncAgentRuntime(
        llm,
        router=AgentRouter(),
        tools={tool.name: tool},
        verifier=verifier,
    )

    result = asyncio.run(runtime.run("Check work order WO-123"))

    assert tool.calls == [{"work_order_id": "WO-123"}]
    spy.assert_called_once()
    assert result == "Work order WO-123 is open (plumbing)."
    assert llm.prompts == []


def test_verification_failure_returns_review_without_llm_or_retry():
    llm = FakeLLM("retry would use this")
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "missing_work_order_id"})
    )
    runtime = _runtime(llm, tool)

    result = asyncio.run(runtime.run("Need maintenance help"))

    assert result == "The request could not be verified."
    assert len(tool.calls) == 1
    assert llm.prompts == []


def test_missing_work_order_id_uses_real_tool_and_fails_verification():
    llm = FakeLLM("unused")
    runtime = AsyncAgentRuntime(
        llm,
        router=AgentRouter(),
        tools={"work_order_lookup": WorkOrderLookupTool()},
        verifier=ToolVerifier(),
    )

    result = asyncio.run(runtime.run("Show work order status"))

    assert result == "The request could not be verified."
    assert llm.prompts == []


def test_router_extracts_work_order_id():
    decision = AgentRouter().decide(
        AgentRequest(message="Status of work order WO-99", metadata={})
    )

    assert decision.action == AgentAction.USE_TOOL
    assert decision.tool_name == "work_order_lookup"
    assert decision.arguments == {"work_order_id": "WO-99"}


def test_tool_success_observation_reaches_final_response():
    llm = FakeLLM("should not be used")
    tool = RecordingTool(
        ToolResult(
            success=True,
            data={
                "work_order_id": "WO-123",
                "status": "open",
                "issue_type": "plumbing",
            },
        )
    )
    runtime = _runtime(llm, tool)

    result = asyncio.run(runtime.run("Check work order WO-123"))

    assert result == "Work order WO-123 is open (plumbing)."
    assert llm.prompts == []


def test_retryable_failure_retries_once_then_succeeds():
    llm = FakeLLM("should not be used")
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
    runtime = _runtime(llm, tool)

    result = asyncio.run(runtime.run("Check work order WO-123"))

    assert len(tool.calls) == 2
    assert result == "Work order WO-123 is open (plumbing)."
    assert llm.prompts == []


def test_non_retryable_failure_goes_directly_to_review():
    llm = FakeLLM("retry would use this")
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "missing_work_order_id"}, retryable=False)
    )
    runtime = _runtime(llm, tool)

    result = asyncio.run(runtime.run("Need maintenance help"))

    assert result == "The request could not be verified."
    assert len(tool.calls) == 1
    assert llm.prompts == []
