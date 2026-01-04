from __future__ import annotations

import json
import urllib.request
import urllib.error

from app.infra.errors import UpstreamLLMError
from app.llm.base import LLMClient


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str = "llama3.1"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            raise UpstreamLLMError(str(e))

        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            raise UpstreamLLMError("Empty response from Ollama")
        return text
