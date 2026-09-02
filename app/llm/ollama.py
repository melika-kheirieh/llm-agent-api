from __future__ import annotations

import asyncio

import httpx

from app.infra.errors import UpstreamLLMError
from app.llm.async_base import AsyncLLMClient


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
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError) as e:
            raise UpstreamLLMError(str(e)) from e

        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            raise UpstreamLLMError("Empty response from Ollama")
        return text

    async def aclose(self) -> None:
        await self._client.aclose()
