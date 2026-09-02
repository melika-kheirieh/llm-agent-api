import asyncio

from app.agent.llm_router import LlmAgentRouter
from app.agent.router import AgentRouter
from app.infra.config import ROUTER_MODE_KEYWORD, ROUTER_MODE_LLM, settings
from app.infra.container import build_runtime, create_router
from app.infra.errors import ConfigurationError


class _FakeLLM:
    async def generate(self, prompt: str) -> str:
        return '{"action": "direct"}'


def test_default_configuration_uses_keyword_router(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", ROUTER_MODE_KEYWORD)
    runtime = build_runtime(llm=_FakeLLM())

    assert isinstance(runtime.router, AgentRouter)
    assert runtime.router.router_type == ROUTER_MODE_KEYWORD


def test_llm_router_selected_by_configuration(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", ROUTER_MODE_LLM)
    runtime = build_runtime(llm=_FakeLLM())

    assert isinstance(runtime.router, LlmAgentRouter)
    assert runtime.router.router_type == ROUTER_MODE_LLM


def test_explicit_router_overrides_configuration(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", ROUTER_MODE_LLM)
    runtime = build_runtime(llm=_FakeLLM(), router=AgentRouter())

    assert isinstance(runtime.router, AgentRouter)


def test_invalid_router_mode_fails_at_wiring(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", "graph")

    try:
        build_runtime(llm=_FakeLLM())
        raise AssertionError("expected ConfigurationError")
    except ConfigurationError as exc:
        assert "Unsupported ROUTER_MODE" in str(exc)


def test_both_routers_satisfy_router_interface():
    llm = _FakeLLM()
    keyword = create_router(ROUTER_MODE_KEYWORD, llm)
    llm_router = create_router(ROUTER_MODE_LLM, llm)

    assert isinstance(keyword, AgentRouter)
    assert isinstance(llm_router, LlmAgentRouter)
    for router in (keyword, llm_router):
        assert asyncio.iscoroutinefunction(router.route)
        assert router.router_type in {ROUTER_MODE_KEYWORD, ROUTER_MODE_LLM}
