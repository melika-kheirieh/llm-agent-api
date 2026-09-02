import asyncio
import uuid

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.router import AgentRouter
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.db.repo import get_trace, init_db, save_trace
from app.observability.trace import ExecutionTrace


class FakeLLM:
    async def generate(self, prompt: str) -> str:
        return "direct answer"


class RecordingTool:
    name = "work_order_lookup"

    def __init__(self, result: ToolResult):
        self.result = result

    async def execute(self, arguments: dict) -> ToolResult:
        return self.result


def _runtime(tool: RecordingTool | None = None) -> AsyncAgentRuntime:
    tools = {tool.name: tool} if tool is not None else {}
    return AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools=tools,
        verifier=ToolVerifier(),
    )


def _persist_and_load(runtime: AsyncAgentRuntime, message: str) -> dict:
    async def _run():
        await init_db()
        _answer, trace = await runtime.run_with_trace(message)
        await save_trace(trace)
        stored = await get_trace(trace.run_id)
        return trace, stored

    return asyncio.run(_run())


def test_direct_run_persists_and_loads_trace():
    trace, stored = _persist_and_load(_runtime(), "hello there")

    assert stored is not None
    assert stored["run_id"] == trace.run_id
    assert stored["terminal_status"] == "completed"
    assert stored["decision"] == "direct"
    assert stored["selected_tool"] is None
    assert stored["outcome"] == "success"
    assert stored["created_at"]


def test_tool_success_persists_trace():
    tool = RecordingTool(
        ToolResult(
            success=True,
            data={"work_order_id": "WO-123", "status": "open", "issue_type": "plumbing"},
        )
    )
    _trace, stored = _persist_and_load(_runtime(tool), "Check work order WO-123")

    assert stored["terminal_status"] == "completed"
    assert stored["decision"] == "use_tool"
    assert stored["selected_tool"] == "work_order_lookup"
    assert stored["verification_result"] == "true"
    assert stored["attempts"] == 1
    assert stored["outcome"] == "success"


def test_review_failure_persists_trace():
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "missing_work_order_id"})
    )
    _trace, stored = _persist_and_load(_runtime(tool), "Need maintenance help")

    assert stored["terminal_status"] == "needs_human_review"
    assert stored["decision"] == "use_tool"
    assert stored["verification_result"] == "false"
    assert stored["outcome"] == "needs_human_review"
    assert stored["failure_class"] == "verification_failed"


def test_get_run_unknown_id_returns_404(client):
    resp = client.get(f"/runs/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "run not found"


def test_get_run_returns_persisted_trace(client):
    trace = ExecutionTrace(
        run_id=str(uuid.uuid4()),
        request_id="req",
        terminal_status="completed",
        decision="direct",
        outcome="success",
    )
    async def _save():
        await init_db()
        await save_trace(trace)

    asyncio.run(_save())

    resp = client.get(f"/runs/{trace.run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == trace.run_id
    assert data["terminal_status"] == "completed"
    assert data["decision"] == "direct"
    assert "response" not in data
