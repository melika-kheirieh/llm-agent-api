from abc import ABC, abstractmethod


class AsyncLLMClient(ABC):
    """Async boundary for model providers.

    Providers should implement this interface without leaking vendor-specific
    clients into the agent runtime.
    """

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release provider HTTP resources. Default is a no-op."""
        return None
