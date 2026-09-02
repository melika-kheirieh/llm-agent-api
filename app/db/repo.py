from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.config import settings
from app.infra.errors import DatabaseError
from app.db.models import Base, ChatMessage


def _async_database_url(url: str) -> str:
    if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return "sqlite+aiosqlite://" + url[len("sqlite://") :]
    return url


engine = create_async_engine(_async_database_url(settings.database_url), future=True)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def init_db() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        raise DatabaseError(str(e))


async def close_db() -> None:
    await engine.dispose()


async def save_chat(message: str, response: str) -> None:
    try:
        async with SessionLocal() as session:
            session.add(ChatMessage(message=message, response=response))
            await session.commit()
    except Exception as e:
        raise DatabaseError(str(e))
