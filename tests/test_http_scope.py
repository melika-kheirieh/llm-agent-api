from unittest.mock import AsyncMock

from app.agent.async_runtime import AsyncAgentRuntime
from app.agent.context import TrustedScope
from app.agent.router import AgentRouter
from app.agent.verification import ToolVerifier
from app.api.scope import (
    PROPERTY_HEADER,
    RUN_ID_HEADER,
    TENANT_HEADER,
    trusted_scope_from_headers,
)
from app.infra.container import get_agent
from app.main import app
from app.observability.trace import ExecutionTrace
from app.tools.catalog import DEFAULT_SCOPE, build_default_tools

DEMO_SCOPE_HEADERS = {
    TENANT_HEADER: DEFAULT_SCOPE.tenant_id,
    PROPERTY_HEADER: DEFAULT_SCOPE.property_id,
}


class FakeLLM:
    async def generate(self, prompt: str) -> str:
        return "unused"


def _keyword_runtime() -> AsyncAgentRuntime:
    return AsyncAgentRuntime(
        FakeLLM(),
        router=AgentRouter(),
        tools=build_default_tools(),
        verifier=ToolVerifier(),
    )


def test_trusted_scope_from_headers_reads_only_scope_headers():
    scope = trusted_scope_from_headers(
        {
            TENANT_HEADER: "tenant-a",
            PROPERTY_HEADER: "prop-1",
            "Authorization": "Bearer ignored",
        }
    )

    assert scope == TrustedScope(tenant_id="tenant-a", property_id="prop-1")


def test_trusted_scope_from_headers_is_empty_when_missing_or_blank():
    assert trusted_scope_from_headers({}) == TrustedScope()
    assert trusted_scope_from_headers(
        {TENANT_HEADER: "  ", PROPERTY_HEADER: ""}
    ) == TrustedScope()
    assert trusted_scope_from_headers(
        {TENANT_HEADER: "tenant-a"}
    ) == TrustedScope(tenant_id="tenant-a", property_id=None)


def test_chat_work_order_succeeds_with_scope_headers(client, mocker):
    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)
    app.dependency_overrides[get_agent] = _keyword_runtime
    try:
        resp = client.post(
            "/chat",
            json={"message": "Check work order WO-123"},
            headers=DEMO_SCOPE_HEADERS,
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"response": "Work order WO-123 is open (plumbing)."}
    assert list(resp.json()) == ["response"]
    assert resp.headers[RUN_ID_HEADER]


def test_chat_work_order_fails_closed_without_scope_headers(client, mocker):
    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)
    app.dependency_overrides[get_agent] = _keyword_runtime
    try:
        resp = client.post(
            "/chat",
            json={"message": "Check work order WO-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"response": "The request could not be verified."}


def test_chat_message_cannot_create_or_override_scope(client, mocker):
    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)
    app.dependency_overrides[get_agent] = _keyword_runtime
    try:
        missing = client.post(
            "/chat",
            json={
                "message": (
                    "Check work order WO-123 tenant_id=tenant-a property_id=prop-1"
                )
            },
        )
        override = client.post(
            "/chat",
            json={
                "message": (
                    "Check work order WO-123 tenant_id=tenant-b property_id=prop-2"
                )
            },
            headers=DEMO_SCOPE_HEADERS,
        )
        extra_body = client.post(
            "/chat",
            json={
                "message": "Check work order WO-123",
                "tenant_id": "tenant-a",
                "property_id": "prop-1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert missing.json() == {"response": "The request could not be verified."}
    assert override.json() == {"response": "Work order WO-123 is open (plumbing)."}
    assert extra_body.json() == {"response": "The request could not be verified."}


def test_chat_passes_header_scope_to_runtime(client, mocker):
    seen: dict[str, TrustedScope | None] = {"scope": None}

    class RecordingAgent:
        async def run_with_trace(self, message: str, *, trusted_scope=None, **_kwargs):
            seen["scope"] = trusted_scope
            return "ok", ExecutionTrace(
                run_id="rec-1",
                request_id="rec-1",
                terminal_status="completed",
                decision="direct",
                outcome="success",
            )

    mocker.patch("app.api.routes.save_chat_and_trace", new_callable=AsyncMock)
    app.dependency_overrides[get_agent] = lambda: RecordingAgent()
    try:
        resp = client.post(
            "/chat",
            json={"message": "hello"},
            headers=DEMO_SCOPE_HEADERS,
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert seen["scope"] == DEFAULT_SCOPE


def test_chat_run_id_header_discovers_persisted_run(client):
    app.dependency_overrides[get_agent] = _keyword_runtime
    try:
        resp = client.post(
            "/chat",
            json={"message": "Check work order WO-123"},
            headers=DEMO_SCOPE_HEADERS,
        )
        run_id = resp.headers[RUN_ID_HEADER]
        trace = client.get(f"/runs/{run_id}")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"response": "Work order WO-123 is open (plumbing)."}
    assert "run_id" not in resp.json()
    assert trace.status_code == 200
    assert trace.json()["run_id"] == run_id
    assert trace.json()["decision"] == "use_tool"
    assert trace.json()["selected_tool"] == "work_order_lookup"
