from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.config import settings
from app.infra.errors import DatabaseError
from app.db.models import AgentRun, Base, ChatMessage
from app.observability.trace import ExecutionTrace


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


def _run_to_dict(row: AgentRun) -> dict:
    created_at = row.created_at.isoformat() if row.created_at is not None else None
    return {
        "run_id": row.run_id,
        "terminal_status": row.terminal_status,
        "decision": row.decision,
        "selected_tool": row.selected_tool,
        "verification_result": row.verification_result,
        "attempts": row.attempts,
        "retry_count": row.retry_count,
        "outcome": row.outcome,
        "failure_class": row.failure_class,
        "created_at": created_at,
    }


async def save_trace(trace: ExecutionTrace) -> None:
    try:
        async with SessionLocal() as session:
            session.add(
                AgentRun(
                    run_id=trace.run_id,
                    terminal_status=trace.terminal_status,
                    decision=trace.decision,
                    selected_tool=trace.selected_tool,
                    verification_result=trace.verification_result,
                    attempts=trace.attempts,
                    retry_count=trace.retry_count,
                    outcome=trace.outcome,
                    failure_class=trace.failure_class,
                )
            )
            await session.commit()
    except Exception as e:
        raise DatabaseError(str(e))


async def get_trace(run_id: str) -> dict | None:
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(AgentRun).where(AgentRun.run_id == run_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _run_to_dict(row)
    except Exception as e:
        raise DatabaseError(str(e))
