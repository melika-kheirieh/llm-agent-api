from app.llm.async_base import AsyncLLMClient


class AsyncAgentRuntime:
    """Minimal async execution boundary for future agent orchestration."""

    def __init__(self, llm: AsyncLLMClient):
        self.llm = llm

    async def run(self, prompt: str) -> str:
        return await self.llm.generate(prompt)
