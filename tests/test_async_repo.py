import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text

from app.db.models import ChatMessage
from app.db.repo import (
    SessionLocal,
    _async_database_url,
    get_trace,
    init_db,
    save_chat,
    save_chat_and_trace,
    save_trace,
)
from app.db.url import async_database_url
from app.infra.errors import ConfigurationError, DatabaseError
from app.observability.trace import ExecutionTrace


def _trace(run_id: str | None = None) -> ExecutionTrace:
    return ExecutionTrace(
        run_id=run_id or str(uuid.uuid4()),
        request_id="req",
        terminal_status="completed",
        decision="direct",
        outcome="success",
    )


async def _chat_row(message: str) -> ChatMessage | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(ChatMessage).where(ChatMessage.message == message)
        )
        return result.scalar_one_or_none()


def test_async_database_url_upgrades_sqlite():
    assert (
        _async_database_url("sqlite:///./app.db") == "sqlite+aiosqlite:///./app.db"
    )


def test_async_database_url_keeps_aiosqlite():
    url = "sqlite+aiosqlite:///./app.db"
    assert _async_database_url(url) == url


def test_async_database_url_upgrades_postgres():
    assert (
        async_database_url("postgresql://agent:agent@localhost:5432/agent")
        == "postgresql+asyncpg://agent:agent@localhost:5432/agent"
    )
    assert (
        async_database_url("postgres://agent:agent@db:5432/agent")
        == "postgresql+asyncpg://agent:agent@db:5432/agent"
    )
    already = "postgresql+asyncpg://agent:agent@db:5432/agent"
    assert async_database_url(already) == already


def test_async_database_url_passes_through_unknown_schemes():
    url = "mysql+aiomysql://user:pass@localhost/app"
    assert async_database_url(url) == url


def test_async_database_url_rejects_blank():
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        async_database_url("  ")


def test_save_chat_wraps_commit_failure(mocker):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=RuntimeError("disk I/O error"))
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    mocker.patch("app.db.repo.SessionLocal", return_value=session)

    with pytest.raises(DatabaseError, match="disk I/O error"):
        asyncio.run(save_chat("hi", "there"))

    session.commit.assert_awaited_once()


def test_save_chat_and_trace_commits_once(mocker):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    mocker.patch("app.db.repo.SessionLocal", return_value=session)

    asyncio.run(save_chat_and_trace("hi", "there", _trace()))

    assert session.add.call_count == 2
    session.commit.assert_awaited_once()


def test_save_chat_and_trace_persists_both_rows():
    message = f"txn-ok-{uuid.uuid4()}"
    trace = _trace()

    async def _run():
        await init_db()
        await save_chat_and_trace(message, "echo", trace)
        chat = await _chat_row(message)
        stored = await get_trace(trace.run_id)
        return chat, stored

    chat, stored = asyncio.run(_run())

    assert chat is not None
    assert chat.response == "echo"
    assert stored is not None
    assert stored["run_id"] == trace.run_id
    assert stored["decision"] == "direct"
    assert stored["events"] == []


def test_trace_persist_failure_does_not_commit_chat():
    run_id = str(uuid.uuid4())
    message = f"txn-fail-{run_id}"

    async def _run():
        await init_db()
        await save_trace(_trace(run_id))
        with pytest.raises(DatabaseError):
            await save_chat_and_trace(message, "should-not-commit", _trace(run_id))
        return await _chat_row(message), await get_trace(run_id)

    chat, stored = asyncio.run(_run())

    assert chat is None
    assert stored is not None
    assert stored["run_id"] == run_id


def test_init_db_applies_alembic_migrations():
    async def _run():
        await init_db()
        async with SessionLocal() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one()

    assert asyncio.run(_run()) == "001_initial"
