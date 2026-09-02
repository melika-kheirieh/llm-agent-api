import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

_TEST_DB = ROOT / ".pytest-app.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"

from app.infra.container import get_agent  # noqa: E402
from app.infra.errors import UpstreamLLMError  # noqa: E402
from app.main import app  # noqa: E402
from app.observability.trace import ExecutionTrace  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clean_test_database():
    _TEST_DB.unlink(missing_ok=True)
    yield
    _TEST_DB.unlink(missing_ok=True)


class FakeAgent:
    def __init__(self, mode="ok"):
        self.mode = mode

    async def run(self, message: str) -> str:
        if self.mode == "ok":
            return f"echo: {message}"
        if self.mode == "llm_error":
            raise UpstreamLLMError("boom")
        raise RuntimeError("unexpected")

    async def run_with_trace(self, message: str) -> tuple[str, ExecutionTrace]:
        text = await self.run(message)
        return text, ExecutionTrace(
            run_id="test",
            request_id="test",
            terminal_status="completed",
            decision="direct",
            outcome="success",
        )


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


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
