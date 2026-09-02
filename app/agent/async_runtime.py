from app.agent.schemas import Analysis
from app.llm.async_base import AsyncLLMClient


class AsyncAgentRuntime:
    """Async execution boundary for the chat agent pipeline."""

    def __init__(self, llm: AsyncLLMClient):
        self.llm = llm

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    async def respond(self, message: str, analysis: Analysis) -> str:
        prompt = f"Answer clearly.\n\nUser: {message}"
        return (await self.llm.generate(prompt)).strip()

    async def run(self, message: str) -> str:
        analysis = self.analyze(message)
        # hook: maybe_use_tool(message, analysis)
        return await self.respond(message, analysis)
