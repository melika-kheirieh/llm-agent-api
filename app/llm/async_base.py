from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from app.llm.structured import parse_structured_output

TSchema = TypeVar("TSchema", bound=BaseModel)


class AsyncLLMClient(ABC):
    """Async boundary for model providers.

    Providers should implement this interface without leaking vendor-specific
    clients into the agent runtime. generate_structured owns JSON/schema
    parsing so callers receive a typed model, not a raw string.
    """

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError

    async def generate_structured(
        self, prompt: str, schema: type[TSchema]
    ) -> TSchema:
        """Return a Pydantic instance. Default path is generate() plus parse."""
        text = await self.generate(prompt)
        return parse_structured_output(text, schema)

    async def aclose(self) -> None:
        """Release provider HTTP resources. Default is a no-op."""
        return None
