import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repo import _async_database_url, save_chat
from app.infra.errors import DatabaseError


def test_async_database_url_upgrades_sqlite():
    assert (
        _async_database_url("sqlite:///./app.db") == "sqlite+aiosqlite:///./app.db"
    )


def test_async_database_url_keeps_aiosqlite():
    url = "sqlite+aiosqlite:///./app.db"
    assert _async_database_url(url) == url


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
