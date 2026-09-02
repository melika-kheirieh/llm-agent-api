from unittest.mock import AsyncMock

from app.api.scope import RUN_ID_HEADER
from app.infra.errors import DatabaseError


def test_chat_success(client, mocker, override_agent_ok):
    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)

    resp = client.post("/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert resp.json() == {"response": "echo: hello"}
    assert resp.headers[RUN_ID_HEADER] == "test"


def test_chat_empty_message(client, override_agent_ok):
    resp = client.post("/chat", json={"message": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "message is required"
    assert RUN_ID_HEADER not in resp.headers


def test_chat_llm_failure(client, override_agent_llm_error):
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "LLM failure"
    assert RUN_ID_HEADER not in resp.headers


def test_chat_persists(mocker, client, override_agent_ok):
    spy = mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)
    client.post("/chat", json={"message": "hi"})
    spy.assert_awaited_once()


def test_chat_missing_message(client):
    resp = client.post("/chat", json={})
    assert resp.status_code == 422


def test_chat_internal_error(client, mocker):
    from app.infra.container import get_agent
    from app.main import app

    class BrokeAgent:
        async def run(self, message: str, **_kwargs):
            raise RuntimeError("Boom")

        async def run_with_trace(self, message: str, **_kwargs):
            raise RuntimeError("Boom")

    app.dependency_overrides[get_agent] = lambda: BrokeAgent()

    try:
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 500
    finally:
        app.dependency_overrides.clear()


def test_chat_response_shape(client, mocker, override_agent_ok):
    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)

    resp = client.post("/chat", json={"message": "hi"})
    data = resp.json()

    assert list(data) == ["response"]
    assert isinstance(data["response"], str)
    assert "run_id" not in data
    assert resp.headers[RUN_ID_HEADER] == "test"


def test_chat_persistence_failure(client, mocker, override_agent_ok):
    mocker.patch(
        "app.api.routes.save_chat_and_trace",
        new_callable=AsyncMock,
        side_effect=DatabaseError("db down"),
    )

    resp = client.post("/chat", json={"message": "hi"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Database unavailable"
    assert RUN_ID_HEADER not in resp.headers
