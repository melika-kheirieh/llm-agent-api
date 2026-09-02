from __future__ import annotations

import asyncio
from typing import TypeVar

from openai import APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

from app.infra.errors import ModelError, ModelTimeout
from app.llm.async_base import AsyncLLMClient
from app.llm.structured import parse_structured_output

TSchema = TypeVar("TSchema", bound=BaseModel)


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

    async def generate_structured(
        self, prompt: str, schema: type[TSchema]
    ) -> TSchema:
        try:
            resp = await self.client.responses.create(
                model=self.model,
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
            text = getattr(resp, "output_text", None)
        except asyncio.CancelledError:
            raise
        except (TimeoutError, APITimeoutError) as e:
            raise ModelTimeout(str(e)) from e
        except Exception:
            return await AsyncLLMClient.generate_structured(self, prompt, schema)

        if not isinstance(text, str) or not text.strip():
            return await AsyncLLMClient.generate_structured(self, prompt, schema)
        return parse_structured_output(text, schema)

    async def aclose(self) -> None:
        await self.client.close()
