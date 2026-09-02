import asyncio

from app.agent.schemas import Analysis
from app.infra.errors import UpstreamLLMError
from app.llm.async_base import AsyncLLMClient


class AsyncAgentRuntime:
    """Async execution boundary for the chat agent pipeline."""

    def __init__(self, llm: AsyncLLMClient, timeout_seconds: float = 60.0):
        self.llm = llm
        self.timeout_seconds = timeout_seconds

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    async def respond(self, message: str, analysis: Analysis) -> str:
        prompt = f"Answer clearly.\n\nUser: {message}"
        return (await self.llm.generate(prompt)).strip()

    async def run(self, message: str) -> str:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                analysis = self.analyze(message)
                # hook: maybe_use_tool(message, analysis)
                return await self.respond(message, analysis)
        except TimeoutError as e:
            raise UpstreamLLMError("LLM request timed out") from e

    async def aclose(self) -> None:
        aclose = getattr(self.llm, "aclose", None)
        if aclose is not None:
            await aclose()
