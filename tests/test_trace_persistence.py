import asyncio
import json
import uuid

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.router import AgentRouter
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.db.repo import get_trace, init_db, save_chat_and_trace, save_trace
from app.evaluation.agent_cases import (
    DIRECT_SUCCESS_EVENTS,
    RETRY_THEN_SUCCESS_EVENTS,
    TOOL_FAILURE_EVENTS,
    TOOL_SUCCESS_EVENTS,
)
from app.observability.events import TraceEvent
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


def _runtime(tool: RecordingTool | None = None) -> AsyncAgentRuntime:
    tools = {tool.name: tool} if tool is not None else {}
    return AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools=tools,
        verifier=ToolVerifier(),
    )


def _persist_and_load(
    runtime: AsyncAgentRuntime, message: str, **run_kwargs
) -> tuple[ExecutionTrace, dict]:
    async def _run():
        await init_db()
        _answer, trace = await runtime.run_with_trace(message, **run_kwargs)
        await save_trace(trace)
        stored = await get_trace(trace.run_id)
        return trace, stored

    return asyncio.run(_run())


def _event_names(stored: dict) -> tuple[str, ...]:
    return tuple(event["name"] for event in stored["events"])


def test_direct_run_persists_and_loads_trace():
    trace, stored = _persist_and_load(_runtime(), "hello there")

    assert stored is not None
    assert stored["run_id"] == trace.run_id
    assert stored["terminal_status"] == "completed"
    assert stored["decision"] == "direct"
    assert stored["selected_tool"] is None
    assert stored["outcome"] == "success"
    assert stored["created_at"]
    assert _event_names(stored) == DIRECT_SUCCESS_EVENTS
    assert "router_type" not in stored
    assert "routing_ms" not in stored


def test_tool_success_persists_trace():
    tool = RecordingTool(
        ToolResult(
            success=True,
            data=scoped_work_order_data(),
        )
    )
    trace, stored = _persist_and_load(
        _runtime(tool),
        "Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
    )

    assert stored["terminal_status"] == "completed"
    assert stored["decision"] == "use_tool"
    assert stored["selected_tool"] == "work_order_lookup"
    assert stored["verification_result"] == "true"
    assert stored["attempts"] == 1
    assert stored["outcome"] == "success"
    assert _event_names(stored) == TOOL_SUCCESS_EVENTS
    assert [event["order"] for event in stored["events"]] == list(
        range(len(stored["events"]))
    )
    payload = json.dumps(stored)
    assert "tenant_id" not in payload
    assert "property_id" not in payload
    assert "plumbing" not in payload
    assert trace.events[0].metadata.get("router_type") == "keyword"


def test_review_failure_persists_trace():
    tool = RecordingTool(
        ToolResult(success=False, data={"error": "missing_work_order_id"})
    )
    _trace, stored = _persist_and_load(_runtime(tool), "Need maintenance help")

    assert stored["terminal_status"] == "needs_human_review"
    assert stored["decision"] == "use_tool"
    assert stored["verification_result"] == "false"
    assert stored["outcome"] == "needs_human_review"
    assert stored["failure_class"] == "tool_error"
    assert _event_names(stored) == TOOL_FAILURE_EVENTS
    failed = next(event for event in stored["events"] if event["name"] == "tool_failed")
    assert failed["metadata"]["error"] == "missing_work_order_id"
    assert "tenant_id" not in failed["metadata"]


def test_retry_flow_persists_event_order():
    tool = RecordingTool(
        [
            ToolResult(success=False, data={"error": "temporary"}, retryable=True),
            ToolResult(success=True, data=scoped_work_order_data()),
        ]
    )
    trace, stored = _persist_and_load(
        _runtime(tool),
        "Check work order WO-123",
        trusted_scope=DEFAULT_SCOPE,
    )

    assert _event_names(stored) == RETRY_THEN_SUCCESS_EVENTS
    assert [event["order"] for event in stored["events"]] == [
        event.order for event in trace.events
    ]
    recovery = next(
        event for event in stored["events"] if event["name"] == "recovery_decision"
    )
    assert recovery["metadata"]["action"] == "retry"


def test_persisted_events_drop_sensitive_metadata():
    trace = ExecutionTrace(
        run_id=str(uuid.uuid4()),
        request_id="req",
        terminal_status="needs_human_review",
        decision="use_tool",
        selected_tool="work_order_lookup",
        outcome="needs_human_review",
        failure_class="tool_error",
        events=(
            TraceEvent(
                name="tool_failed",
                order=0,
                timestamp=1.5,
                metadata={
                    "error": "cross_tenant",
                    "tool_name": "work_order_lookup",
                    "tenant_id": "tenant-a",
                    "property_id": "prop-1",
                    "data": scoped_work_order_data(),
                    "arguments": {"work_order_id": "WO-999"},
                },
            ),
        ),
    )

    async def _run():
        await init_db()
        await save_trace(trace)
        return await get_trace(trace.run_id)

    stored = asyncio.run(_run())

    assert stored is not None
    assert len(stored["events"]) == 1
    event = stored["events"][0]
    assert event["order"] == 0
    assert event["name"] == "tool_failed"
    assert event["timestamp"] == 1.5
    assert event["metadata"] == {
        "error": "cross_tenant",
        "tool_name": "work_order_lookup",
    }
    dumped = json.dumps(stored)
    assert "tenant_id" not in dumped
    assert "property_id" not in dumped
    assert "tenant-a" not in dumped


def test_chat_and_trace_persist_events_together():
    runtime = _runtime()

    async def _run():
        await init_db()
        answer, trace = await runtime.run_with_trace("hello there")
        await save_chat_and_trace("hello there", answer, trace)
        return await get_trace(trace.run_id)

    stored = asyncio.run(_run())

    assert stored is not None
    assert _event_names(stored) == DIRECT_SUCCESS_EVENTS


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
    assert data["events"] == []
    assert "router_type" not in data


def test_get_run_returns_persisted_events(client):
    tool = RecordingTool(
        ToolResult(success=True, data=scoped_work_order_data())
    )

    async def _run():
        await init_db()
        _answer, trace = await _runtime(tool).run_with_trace(
            "Check work order WO-123",
            trusted_scope=DEFAULT_SCOPE,
        )
        await save_trace(trace)
        return trace.run_id

    run_id = asyncio.run(_run())
    resp = client.get(f"/runs/{run_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert [event["name"] for event in data["events"]] == list(TOOL_SUCCESS_EVENTS)
    assert "response" not in data
    assert "tenant_id" not in json.dumps(data)
