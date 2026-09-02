import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import ContextPolicy, HistoryTurn, TrustedScope
from app.agent.llm_router import ROUTING_PROMPT_MARKER, LlmAgentRouter
from app.agent.router import AgentRouter
from app.agent.tools import ToolResult
from app.agent.verification import ToolVerifier
from app.tools.catalog import DEFAULT_SCOPE
from app.tools.work_order import WorkOrderLookupTool


class FakeLLM:
    def __init__(self, text: str = "generated answer"):
        self.text = text
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.text


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


def _runtime(llm: FakeLLM | None = None) -> AsyncAgentRuntime:
    return AsyncAgentRuntime(
        llm or FakeLLM(),
        router=AgentRouter(),
        tools={"work_order_lookup": WorkOrderLookupTool()},
        verifier=ToolVerifier(),
        context_policy=ContextPolicy(max_history=4),
    )


def test_same_thread_receives_prior_turns_in_answer_context():
    runtime = _runtime()
    asyncio.run(runtime.run("hello there", thread_id="thread-a"))
    _answer, state = asyncio.run(
        runtime.run_detailed("follow up", thread_id="thread-a")
    )

    history = state.context.answer.history
    assert [turn.content for turn in history] == ["hello there", "generated answer"]
    assert [turn.order for turn in history] == [0, 1]
    assert state.context.execution.thread_id == "thread-a"


def test_different_thread_cannot_access_previous_context():
    runtime = _runtime()
    asyncio.run(runtime.run("hello there", thread_id="thread-a"))
    _answer, state = asyncio.run(
        runtime.run_detailed("follow up", thread_id="thread-b")
    )

    assert state.context.answer.history == ()
    assert state.context.execution.thread_id == "thread-b"


def test_history_limit_is_enforced_on_thread_buffer():
    runtime = AsyncAgentRuntime(
        FakeLLM("ok"),
        context_policy=ContextPolicy(max_history=2),
    )
    asyncio.run(runtime.run("one", thread_id="t"))
    asyncio.run(runtime.run("two", thread_id="t"))
    _answer, state = asyncio.run(runtime.run_detailed("three", thread_id="t"))

    assert [turn.content for turn in state.context.answer.history] == ["two", "ok"]
    assert [turn.order for turn in state.context.answer.history] == [0, 1]


def test_explicit_history_order_is_deterministic():
    runtime = _runtime()
    history = (
        HistoryTurn(role="user", content="first", order=9),
        HistoryTurn(role="assistant", content="second", order=3),
        HistoryTurn(role="user", content="third", order=1),
    )
    _answer, state = asyncio.run(
        runtime.run_detailed("now", history=history)
    )

    assert [turn.content for turn in state.context.answer.history] == [
        "first",
        "second",
        "third",
    ]
    assert [turn.order for turn in state.context.answer.history] == [0, 1, 2]


def test_missing_scope_does_not_break_execution():
    runtime = _runtime()
    answer, state = asyncio.run(runtime.run_detailed("hello there"))

    assert answer == "generated answer"
    assert state.context.trusted_scope == TrustedScope()
    assert state.context.execution.thread_id is None


def test_untrusted_tool_data_is_not_promoted():
    tool_result = ToolResult(
        success=True,
        data={"work_order_id": "WO-123", "status": "lost", "issue_type": "plumbing"},
    )

    class Scripted:
        name = "work_order_lookup"

        async def execute(self, arguments: dict, *, trusted_scope=None) -> ToolResult:
            return tool_result

    runtime = AsyncAgentRuntime(
        FakeLLM("unused"),
        router=AgentRouter(),
        tools={"work_order_lookup": Scripted()},
        verifier=ToolVerifier(),
    )
    _answer, state = asyncio.run(
        runtime.run_detailed("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    assert state.verification_result is False
    assert state.observations[0].data["status"] == "lost"
    assert state.context.answer.evidence == ()


def test_verified_tool_evidence_is_trusted():
    runtime = _runtime()
    _answer, state = asyncio.run(
        runtime.run_detailed("Check work order WO-123", trusted_scope=DEFAULT_SCOPE)
    )

    evidence = state.context.answer.evidence
    assert len(evidence) == 1
    assert evidence[0].trusted is True
    assert "tenant_id" not in evidence[0].data
    assert "property_id" not in evidence[0].data
    assert evidence[0].data["work_order_id"] == "WO-123"
    assert evidence[0].data["status"] == "open"
    assert state.observations[0].data["tenant_id"] == DEFAULT_SCOPE.tenant_id
    assert state.context.trusted_scope == DEFAULT_SCOPE


def test_backend_scope_is_not_overridden_by_tool_or_llm():
    runtime = _runtime()
    scope = TrustedScope(tenant_id="tenant-backend", property_id="prop-9")
    _answer, state = asyncio.run(
        runtime.run_detailed(
            "Check work order WO-123",
            trusted_scope=scope,
        )
    )

    assert state.context.trusted_scope == scope
    assert state.decision.arguments == {"work_order_id": "WO-123"}
    assert "tenant_id" not in (state.decision.arguments or {})
    assert "property_id" not in (state.decision.arguments or {})
    assert state.verification_result is False
    assert state.observations[0].data.get("error") == "cross_tenant"
    assert "status" not in state.observations[0].data


def test_router_prompt_omits_history_used_for_answers():
    llm = RoutingFakeLLM('{"action": "direct"}')
    runtime = AsyncAgentRuntime(
        llm,
        router=LlmAgentRouter(llm),
        context_policy=ContextPolicy(max_history=8),
    )
    history = (
        HistoryTurn(role="user", content="secret prior", order=0),
        HistoryTurn(role="assistant", content="prior answer", order=1),
    )
    asyncio.run(runtime.run("hello there", history=history))

    routing_prompts = [p for p in llm.prompts if ROUTING_PROMPT_MARKER in p]
    answer_prompts = [p for p in llm.prompts if ROUTING_PROMPT_MARKER not in p]
    assert routing_prompts
    assert "secret prior" not in routing_prompts[0]
    assert "prior answer" not in routing_prompts[0]
    assert "secret prior" in answer_prompts[0]
    assert "prior answer" in answer_prompts[0]
