from __future__ import annotations

from openai import AsyncOpenAI

from app.infra.errors import UpstreamLLMError
from app.llm.async_base import AsyncLLMClient


class OpenAIClient(AsyncLLMClient):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ):
        # base_url optional: OpenAI default if None
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model

    async def generate(self, prompt: str) -> str:
        try:
            resp = await self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            text = getattr(resp, "output_text", None)
        except Exception as e:
            raise UpstreamLLMError(str(e))

        if not isinstance(text, str) or not text.strip():
            raise UpstreamLLMError("Empty response from OpenAI")

        return text
