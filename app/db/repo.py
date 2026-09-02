import json

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.config import settings
from app.infra.errors import DatabaseError
from app.db.migrate import upgrade_to_head
from app.db.models import AgentRun, AgentRunEvent, ChatMessage
from app.db.url import async_database_url
from app.observability.events import persisted_event_payload
from app.observability.trace import ExecutionTrace


def _async_database_url(url: str) -> str:
    return async_database_url(url)


engine = create_async_engine(async_database_url(settings.database_url), future=True)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def init_db() -> None:
    try:
        async with engine.connect() as conn:
            await conn.run_sync(upgrade_to_head)
            await conn.commit()
    except Exception as e:
        raise DatabaseError(str(e))


async def close_db() -> None:
    await engine.dispose()


async def ping_db() -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        raise DatabaseError(str(e))


def _agent_run(trace: ExecutionTrace) -> AgentRun:
    return AgentRun(
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


def _event_rows(trace: ExecutionTrace) -> list[AgentRunEvent]:
    rows = []
    for event in trace.events:
        payload = persisted_event_payload(event)
        rows.append(
            AgentRunEvent(
                run_id=trace.run_id,
                event_order=payload["order"],
                name=payload["name"],
                timestamp=payload["timestamp"],
                metadata_json=json.dumps(payload["metadata"]),
            )
        )
    return rows


def _add_trace(session: AsyncSession, trace: ExecutionTrace) -> None:
    session.add(_agent_run(trace))
    for row in _event_rows(trace):
        session.add(row)


async def save_chat(message: str, response: str) -> None:
    try:
        async with SessionLocal() as session:
            session.add(ChatMessage(message=message, response=response))
            await session.commit()
    except Exception as e:
        raise DatabaseError(str(e))


async def save_chat_and_trace(
    message: str, response: str, trace: ExecutionTrace
) -> None:
    """Persist chat row, run summary, and sanitized events in one transaction."""
    try:
        async with SessionLocal() as session:
            session.add(ChatMessage(message=message, response=response))
            _add_trace(session, trace)
            await session.commit()
    except Exception as e:
        raise DatabaseError(str(e))


def _event_to_dict(row: AgentRunEvent) -> dict:
    try:
        metadata = json.loads(row.metadata_json) if row.metadata_json else {}
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "order": row.event_order,
        "name": row.name,
        "timestamp": row.timestamp,
        "metadata": metadata,
    }


def _run_to_dict(row: AgentRun, events: list[dict] | None = None) -> dict:
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
        "events": events if events is not None else [],
    }


async def save_trace(trace: ExecutionTrace) -> None:
    try:
        async with SessionLocal() as session:
            _add_trace(session, trace)
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
            event_result = await session.execute(
                select(AgentRunEvent)
                .where(AgentRunEvent.run_id == run_id)
                .order_by(AgentRunEvent.event_order)
            )
            events = [_event_to_dict(item) for item in event_result.scalars().all()]
            return _run_to_dict(row, events)
    except Exception as e:
        raise DatabaseError(str(e))
