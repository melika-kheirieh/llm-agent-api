from unittest.mock import AsyncMock

from app.infra.container import get_agent
from app.infra.errors import DatabaseError
from app.main import app


def test_health_succeeds_without_db_or_provider(client, mocker):
    ping = mocker.patch("app.api.routes.ping_db", new_callable=AsyncMock)

    def _boom_agent():
        raise RuntimeError("provider must not be used")

    app.dependency_overrides[get_agent] = _boom_agent
    try:
        resp = client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    ping.assert_not_called()


def test_ready_succeeds_when_db_is_available(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_fails_when_db_is_unavailable(client, mocker):
    mocker.patch(
        "app.api.routes.ping_db",
        new_callable=AsyncMock,
        side_effect=DatabaseError("db down"),
    )

    resp = client.get("/ready")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Database unavailable"
