from __future__ import annotations

import asyncio

from openai import APITimeoutError, AsyncOpenAI

from app.infra.errors import ModelError, ModelTimeout
from app.llm.async_base import AsyncLLMClient


class OpenAIClient(AsyncLLMClient):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ):
        # base_url optional: OpenAI default if None
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self.model = model

    async def generate(self, prompt: str) -> str:
        try:
            resp = await self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            text = getattr(resp, "output_text", None)
        except asyncio.CancelledError:
            raise
        except (TimeoutError, APITimeoutError) as e:
            raise ModelTimeout(str(e)) from e
        except Exception as e:
            raise ModelError(str(e)) from e

        if not isinstance(text, str) or not text.strip():
            raise ModelError("Empty response from OpenAI")

        return text

    async def aclose(self) -> None:
        await self.client.close()
