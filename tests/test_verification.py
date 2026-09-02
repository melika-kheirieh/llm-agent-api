import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.router import AgentRouter
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.tools.work_order import (
    ALLOWED_WORK_ORDER_STATUSES,
    WorkOrderLookupRequest,
    WorkOrderLookupTool,
    WorkOrderObservation,
    WorkOrderResult,
)


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


def _valid_data(work_order_id: str = "WO-123", status: str = "open") -> dict:
    return WorkOrderResult(
        work_order_id=work_order_id,
        status=status,
        issue_type="plumbing",
    ).as_data()


def test_lookup_request_parses_work_order_id():
    request = WorkOrderLookupRequest.from_arguments({"work_order_id": " WO-123 "})
    assert request.work_order_id == "WO-123"


def test_lookup_request_treats_blank_id_as_missing():
    request = WorkOrderLookupRequest.from_arguments({"work_order_id": "  "})
    assert request.work_order_id is None


def test_observation_requires_id_and_status():
    assert WorkOrderObservation.from_data({"work_order_id": "WO-123"}) is None
    assert WorkOrderObservation.from_data({"status": "open"}) is None
    parsed = WorkOrderObservation.from_data(_valid_data())
    assert parsed is not None
    assert parsed.work_order_id == "WO-123"
    assert parsed.status == "open"


def test_valid_work_order_passes_verification():
    result = ToolResult(success=True, data=_valid_data())
    assert ToolVerifier().verify(result, {"work_order_id": "WO-123"}) is True


def test_missing_required_field_fails_verification():
    result = ToolResult(
        success=True,
        data={"work_order_id": "WO-123", "issue_type": "plumbing"},
    )
    assert ToolVerifier().verify(result, {"work_order_id": "WO-123"}) is False


def test_mismatched_work_order_id_fails_verification():
    result = ToolResult(success=True, data=_valid_data("WO-999"))
    assert ToolVerifier().verify(result, {"work_order_id": "WO-123"}) is False


def test_invalid_status_fails_verification():
    result = ToolResult(success=True, data=_valid_data(status="lost"))
    assert "lost" not in ALLOWED_WORK_ORDER_STATUSES
    assert ToolVerifier().verify(result, {"work_order_id": "WO-123"}) is False


def test_unsuccessful_result_fails_without_domain_parse():
    result = ToolResult(success=False, data={"error": "temporary"}, retryable=True)
    assert ToolVerifier().verify(result, {"work_order_id": "WO-123"}) is False


def test_runtime_valid_work_order_succeeds():
    runtime = AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools={"work_order_lookup": WorkOrderLookupTool()},
        verifier=ToolVerifier(),
    )

    answer = asyncio.run(runtime.run("Check work order WO-123"))

    assert answer == "Work order WO-123 is open (plumbing)."


def test_runtime_missing_required_field_goes_to_review():
    tool = RecordingTool(
        ToolResult(success=True, data={"work_order_id": "WO-123"})
    )
    runtime = AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools={tool.name: tool},
        verifier=ToolVerifier(),
    )

    answer = asyncio.run(runtime.run("Check work order WO-123"))

    assert answer == "The request could not be verified."
    assert len(tool.calls) == 1


def test_runtime_mismatched_work_order_id_goes_to_review():
    tool = RecordingTool(ToolResult(success=True, data=_valid_data("WO-999")))
    runtime = AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools={tool.name: tool},
        verifier=ToolVerifier(),
    )

    answer = asyncio.run(runtime.run("Check work order WO-123"))

    assert answer == "The request could not be verified."
    assert tool.calls == [{"work_order_id": "WO-123"}]


def test_runtime_invalid_status_goes_to_review():
    tool = RecordingTool(
        ToolResult(success=True, data=_valid_data(status="unknown"))
    )
    runtime = AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools={tool.name: tool},
        verifier=ToolVerifier(),
    )

    answer = asyncio.run(runtime.run("Check work order WO-123"))

    assert answer == "The request could not be verified."


def test_retryable_tool_failure_still_retries():
    tool = RecordingTool(
        [
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(success=True, data=_valid_data()),
        ]
    )
    runtime = AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools={tool.name: tool},
        verifier=ToolVerifier(),
    )

    answer = asyncio.run(runtime.run("Check work order WO-123"))

    assert len(tool.calls) == 2
    assert answer == "Work order WO-123 is open (plumbing)."
    assert tool.calls == [{"work_order_id": "WO-123"}, {"work_order_id": "WO-123"}]
