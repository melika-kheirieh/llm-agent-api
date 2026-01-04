import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.infra.container import get_agent
from app.infra.errors import UpstreamLLMError


class FakeAgent:
    def __init__(self, mode="ok"):
        self.mode = mode

    def run(self, message: str) -> str:
        if self.mode == "ok":
            return f"echo: {message}"
        if self.mode == "llm_error":
            raise UpstreamLLMError("boom")
        raise RuntimeError("unexpected")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_agent_ok():
    return FakeAgent(mode="ok")


@pytest.fixture
def fake_agent_llm_error():
    return FakeAgent(mode="llm_error")


@pytest.fixture
def override_agent_ok(fake_agent_ok):
    app.dependency_overrides[get_agent] = lambda: fake_agent_ok
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_agent_llm_error(fake_agent_llm_error):
    app.dependency_overrides[get_agent] = lambda: fake_agent_llm_error
    yield
    app.dependency_overrides.clear()
