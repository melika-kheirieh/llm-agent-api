import asyncio

from app.agent.async_runtime import AsyncAgentRuntime
from app.infra.errors import UpstreamLLMError


class FakeLLM:
    def __init__(self, text: str = "generated answer"):
        self.text = text
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.text


def test_runtime_runs_analyze_then_respond():
    llm = FakeLLM("  padded answer  ")
    runtime = AsyncAgentRuntime(llm)

    result = asyncio.run(runtime.run("hello"))

    assert result == "padded answer"
    assert llm.prompts == ["Answer clearly.\n\nUser: hello"]


def test_runtime_analyze_is_local():
    runtime = AsyncAgentRuntime(FakeLLM())

    analysis = runtime.analyze("ignored")

    assert analysis.language == "auto"
    assert analysis.tone == "neutral"
    assert analysis.task_type == "qa"


def test_runtime_propagates_upstream_error():
    class FailingLLM:
        async def generate(self, prompt: str) -> str:
            raise UpstreamLLMError("provider down")

    runtime = AsyncAgentRuntime(FailingLLM())

    try:
        asyncio.run(runtime.run("hello"))
        raise AssertionError("expected UpstreamLLMError")
    except UpstreamLLMError as exc:
        assert "provider down" in str(exc)


def test_runtime_awaits_provider(mocker):
    llm = FakeLLM("ok")
    spy = mocker.spy(llm, "generate")
    runtime = AsyncAgentRuntime(llm)

    asyncio.run(runtime.run("hi"))

    spy.assert_awaited_once()
