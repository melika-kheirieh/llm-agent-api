from __future__ import annotations

import asyncio
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.infra.errors import ModelError, ModelTimeout
from app.llm.async_base import AsyncLLMClient
from app.llm.structured import parse_structured_output

TSchema = TypeVar("TSchema", bound=BaseModel)


class OllamaClient(AsyncLLMClient):
    def __init__(
        self,
        base_url: str,
        model: str = "llama3.1",
        timeout_seconds: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def generate(self, prompt: str) -> str:
        return await self._generate_text(prompt, structured=False)

    async def generate_structured(
        self, prompt: str, schema: type[TSchema]
    ) -> TSchema:
        try:
            text = await self._generate_text(prompt, structured=True)
        except ModelError:
            return await AsyncLLMClient.generate_structured(self, prompt, schema)
        return parse_structured_output(text, schema)

    async def _generate_text(self, prompt: str, *, structured: bool) -> str:
        url = f"{self.base_url}/api/generate"
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if structured:
            payload["format"] = "json"

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx.TimeoutException) as e:
            raise ModelTimeout(str(e)) from e
        except (httpx.HTTPError, ValueError) as e:
            raise ModelError(str(e)) from e

        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            raise ModelError("Empty response from Ollama")
        return text

    async def aclose(self) -> None:
        await self._client.aclose()
