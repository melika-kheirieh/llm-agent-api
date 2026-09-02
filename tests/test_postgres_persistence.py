import asyncio
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.url import async_database_url
from app.observability.events import TraceEvent
from app.observability.trace import ExecutionTrace

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set",
)


def _trace(run_id: str | None = None) -> ExecutionTrace:
    return ExecutionTrace(
        run_id=run_id or str(uuid.uuid4()),
        request_id="req",
        terminal_status="needs_human_review",
        decision="use_tool",
        selected_tool="work_order_lookup",
        outcome="needs_human_review",
        failure_class="tool_error",
        events=(
            TraceEvent(
                name="tool_failed",
                order=0,
                timestamp=1.5,
                metadata={
                    "error": "cross_tenant",
                    "tool_name": "work_order_lookup",
                    "tenant_id": "tenant-a",
                    "property_id": "prop-1",
                },
            ),
        ),
    )


@pytest.fixture
def postgres_db(monkeypatch):
    import app.db.repo as repo

    engine = create_async_engine(
        async_database_url(POSTGRES_URL),
        future=True,
        poolclass=NullPool,
    )
    session_local = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(repo, "engine", engine)
    monkeypatch.setattr(repo, "SessionLocal", session_local)
    return repo, engine


def test_postgres_persists_sanitized_events(postgres_db):
    repo, engine = postgres_db
    trace = _trace()

    async def _run():
        await repo.init_db()
        try:
            await repo.save_trace(trace)
            return await repo.get_trace(trace.run_id)
        finally:
            await engine.dispose()

    stored = asyncio.run(_run())

    assert stored is not None
    assert stored["run_id"] == trace.run_id
    assert stored["failure_class"] == "tool_error"
    assert stored["events"][0]["name"] == "tool_failed"
    assert stored["events"][0]["metadata"] == {
        "error": "cross_tenant",
        "tool_name": "work_order_lookup",
    }
    assert "tenant_id" not in str(stored)
    assert "property_id" not in str(stored)


def test_postgres_chat_and_trace_are_atomic(postgres_db):
    repo, engine = postgres_db
    run_id = str(uuid.uuid4())
    message = f"pg-ok-{run_id}"
    trace = _trace(run_id)

    async def _run():
        await repo.init_db()
        try:
            await repo.save_chat_and_trace(message, "echo", trace)
            stored = await repo.get_trace(run_id)
            await repo.ping_db()
            return stored
        finally:
            await engine.dispose()

    stored = asyncio.run(_run())
    assert stored["run_id"] == run_id
    assert stored["events"][0]["order"] == 0
