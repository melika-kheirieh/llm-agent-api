from app.infra.errors import ConfigurationError

_ASYNC_DRIVER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("sqlite+aiosqlite://", "sqlite+aiosqlite://"),
    ("postgresql+asyncpg://", "postgresql+asyncpg://"),
    ("postgres+asyncpg://", "postgresql+asyncpg://"),
    ("sqlite://", "sqlite+aiosqlite://"),
    ("postgresql://", "postgresql+asyncpg://"),
    ("postgres://", "postgresql+asyncpg://"),
)


def async_database_url(url: str) -> str:
    """Return an async SQLAlchemy URL. Unknown schemes pass through unchanged."""
    value = (url or "").strip()
    if not value:
        raise ConfigurationError("DATABASE_URL is required")
    for prefix, replacement in _ASYNC_DRIVER_PREFIXES:
        if value.startswith(prefix):
            return replacement + value[len(prefix) :]
    return value
