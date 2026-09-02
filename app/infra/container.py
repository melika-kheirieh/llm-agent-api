from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import ContextPolicy
from app.agent.llm_router import LlmAgentRouter
from app.agent.recovery import RecoveryPolicy
from app.agent.router import AgentRouter, Router
from app.agent.tools import AgentTool
from app.agent.verification import ToolVerifier
from app.infra.config import ROUTER_MODE_LLM, normalize_router_mode, settings
from app.llm.async_base import AsyncLLMClient
from app.tools.catalog import build_default_tools

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
    return build_default_tools()


def create_router(
    mode: str,
    llm: AsyncLLMClient,
    *,
    allowed_tools: frozenset[str] | None = None,
    timeout_seconds: float = 60.0,
) -> Router:
    """Build a Router from ROUTER_MODE. Default production mode is keyword."""
    resolved = normalize_router_mode(mode)
    if resolved == ROUTER_MODE_LLM:
        return LlmAgentRouter(
            llm,
            allowed_tools=allowed_tools,
            timeout_seconds=timeout_seconds,
        )
    return AgentRouter()


def _build_runtime() -> AsyncAgentRuntime:
    return build_runtime()


def build_runtime(
    llm: AsyncLLMClient | None = None,
    tools: dict[str, AgentTool] | None = None,
    router: Router | None = None,
) -> AsyncAgentRuntime:
    resolved_llm = llm or _build_llm()
    resolved_tools = _build_tools() if tools is None else tools
    timeout_seconds = float(settings.llm_timeout_seconds)
    resolved_router = router if router is not None else create_router(
        settings.router_mode,
        resolved_llm,
        allowed_tools=frozenset(resolved_tools),
        timeout_seconds=timeout_seconds,
    )
    return AsyncAgentRuntime(
        resolved_llm,
        timeout_seconds=timeout_seconds,
        router=resolved_router,
        tools=resolved_tools,
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
