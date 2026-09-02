import asyncio
import time
from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent.async_runtime import AsyncAgentRuntime
from app.infra.container import close_runtime, get_agent, init_runtime
from app.infra.errors import ModelTimeout
from app.main import app
from app.tools.catalog import DEFAULT_SCOPE, scoped_work_order_data


class SlowLLM:
    def __init__(self, delay: float = 0.2, text: str = "ok"):
        self.delay = delay
        self.text = text
        self.calls = 0

    async def generate(self, prompt: str) -> str:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return self.text

    async def aclose(self) -> None:
        return None


class ForeverLLM:
    def __init__(self):
        self.started = asyncio.Event()

    async def generate(self, prompt: str) -> str:
        self.started.set()
        await asyncio.Event().wait()
        return "unreachable"

    async def aclose(self) -> None:
        return None


def test_runtime_timeout_maps_to_model_timeout():
    runtime = AsyncAgentRuntime(SlowLLM(delay=1.0), timeout_seconds=0.05)

    with pytest.raises(ModelTimeout, match="timed out"):
        asyncio.run(runtime.run("hello"))


def test_runtime_cancellation_is_not_wrapped_as_llm_error():
    llm = ForeverLLM()
    runtime = AsyncAgentRuntime(llm, timeout_seconds=30)

    async def _run():
        task = asyncio.create_task(runtime.run("hello"))
        await llm.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run())


def test_runtime_concurrent_generates_do_not_block():
    runtime = AsyncAgentRuntime(SlowLLM(delay=0.2), timeout_seconds=5)

    async def _run():
        started = time.perf_counter()
        results = await asyncio.gather(runtime.run("a"), runtime.run("b"))
        elapsed = time.perf_counter() - started
        return results, elapsed

    results, elapsed = asyncio.run(_run())

    assert results == ["ok", "ok"]
    assert elapsed < 0.35


def test_runtime_aclose_closes_provider():
    class TrackingLLM:
        def __init__(self):
            self.closed = False

        async def generate(self, prompt: str) -> str:
            return "x"

        async def aclose(self) -> None:
            self.closed = True

    llm = TrackingLLM()
    runtime = AsyncAgentRuntime(llm)
    asyncio.run(runtime.aclose())
    assert llm.closed


def test_container_reuses_runtime_until_closed(mocker):
    mocker.patch("app.infra.container._build_llm", return_value=SlowLLM(delay=0))

    async def _run():
        await close_runtime()
        first = await init_runtime()
        second = get_agent()
        assert first is second
        await close_runtime()
        third = get_agent()
        assert third is not first
        await close_runtime()

    asyncio.run(_run())


def test_chat_concurrent_requests_overlap(mocker):
    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)

    class SlowAgent:
        async def run(self, message: str) -> str:
            await asyncio.sleep(0.2)
            return f"echo: {message}"

        async def run_with_trace(self, message: str):
            from app.observability.trace import ExecutionTrace

            text = await self.run(message)
            return text, ExecutionTrace(
                run_id="test",
                request_id="test",
                terminal_status="completed",
                decision="direct",
                outcome="success",
            )

    async def _run():
        from app.infra.container import get_agent as get_agent_dep

        app.dependency_overrides[get_agent_dep] = lambda: SlowAgent()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                started = time.perf_counter()
                responses = await asyncio.gather(
                    client.post("/chat", json={"message": "a"}),
                    client.post("/chat", json={"message": "b"}),
                )
                elapsed = time.perf_counter() - started
        finally:
            app.dependency_overrides.clear()
        return responses, elapsed

    responses, elapsed = asyncio.run(_run())

    assert all(resp.status_code == 200 for resp in responses)
    assert {resp.json()["response"] for resp in responses} == {"echo: a", "echo: b"}
    assert elapsed < 0.35


class _ValidWorkOrderTool:
    name = "work_order_lookup"

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls = 0

    async def execute(self, arguments: dict, *, trusted_scope=None):
        from app.agent.tools import ToolResult

        self.calls += 1
        await asyncio.sleep(self.delay)
        return ToolResult(
            success=True,
            data=scoped_work_order_data(arguments.get("work_order_id", "WO-123")),
        )


def test_tool_timeout_is_not_model_timeout():
    from app.infra.errors import FailureClass
    from app.observability.trace import trace_from_state

    tool = _ValidWorkOrderTool(delay=0.2)
    runtime = AsyncAgentRuntime(
        SlowLLM(delay=0),
        model_timeout_seconds=5.0,
        tool_timeout_seconds=0.05,
        tools={tool.name: tool},
    )

    answer, state = asyncio.run(
        runtime.run_detailed("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )
    trace = trace_from_state(state)

    assert answer == "The request could not be verified."
    assert trace.failure_class == FailureClass.TOOL_TIMEOUT.value
    assert trace.recovery_decision == "escalate"
    assert trace.retry_count == 1
    assert trace.attempts == 2


def test_slow_tool_does_not_trip_model_timeout():
    tool = _ValidWorkOrderTool(delay=0.2)
    runtime = AsyncAgentRuntime(
        SlowLLM(delay=0),
        model_timeout_seconds=0.05,
        tool_timeout_seconds=1.0,
        tools={tool.name: tool},
    )

    answer = asyncio.run(
        runtime.run("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    assert answer == "Work order WO-123 is open (plumbing)."
    assert tool.calls == 1
