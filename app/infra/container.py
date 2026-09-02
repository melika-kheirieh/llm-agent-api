from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import ContextPolicy
from app.agent.recovery import RecoveryPolicy
from app.agent.router import AgentRouter
from app.agent.tools import AgentTool
from app.agent.verification import ToolVerifier
from app.infra.config import settings
from app.llm.async_base import AsyncLLMClient
from app.tools.work_order import WorkOrderLookupTool

_runtime: AsyncAgentRuntime | None = None


def _build_llm() -> AsyncLLMClient:
    settings.validate_startup()
    provider = settings.llm_provider
    timeout_seconds = float(settings.llm_timeout_seconds)

    if provider == "ollama":
        from app.llm.ollama import OllamaClient

        return OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=timeout_seconds,
        )

    from app.llm.openai import OpenAIClient

    return OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        timeout_seconds=timeout_seconds,
    )


def _build_tools() -> dict[str, AgentTool]:
    work_order = WorkOrderLookupTool()
    return {work_order.name: work_order}


def _build_runtime() -> AsyncAgentRuntime:
    return build_runtime()


def build_runtime(llm: AsyncLLMClient | None = None) -> AsyncAgentRuntime:
    return AsyncAgentRuntime(
        llm or _build_llm(),
        timeout_seconds=float(settings.llm_timeout_seconds),
        router=AgentRouter(),
        tools=_build_tools(),
        verifier=ToolVerifier(),
        recovery=RecoveryPolicy(max_attempts=2),
        context_policy=ContextPolicy(),
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
