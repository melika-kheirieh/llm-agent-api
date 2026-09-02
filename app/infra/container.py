from app.agent.async_runtime import AsyncAgentRuntime
from app.infra.config import settings
from app.llm.async_base import AsyncLLMClient

_runtime: AsyncAgentRuntime | None = None


def _build_llm() -> AsyncLLMClient:
    provider = settings.llm_provider.lower().strip()
    timeout_seconds = settings.llm_timeout_seconds

    if provider == "ollama":
        from app.llm.ollama import OllamaClient

        return OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=timeout_seconds,
        )

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        from app.llm.openai import OpenAIClient

        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_seconds=timeout_seconds,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")


def _build_runtime() -> AsyncAgentRuntime:
    return AsyncAgentRuntime(
        _build_llm(),
        timeout_seconds=settings.llm_timeout_seconds,
    )


def get_agent() -> AsyncAgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime


async def init_runtime() -> AsyncAgentRuntime:
    return get_agent()


async def close_runtime() -> None:
    global _runtime
    runtime, _runtime = _runtime, None
    if runtime is not None:
        await runtime.aclose()
