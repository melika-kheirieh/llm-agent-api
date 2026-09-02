from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.agent.async_runtime import AsyncAgentRuntime
from app.infra.container import get_agent
from app.infra.errors import UpstreamLLMError, DatabaseError
from app.db.repo import get_trace, ping_db, save_chat_and_trace
import logging


router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    agent: AsyncAgentRuntime = Depends(get_agent),
) -> dict:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        response, trace = await agent.run_with_trace(message)
        await save_chat_and_trace(message, response, trace)

        logger.info(
            "chat_success",
            extra={
                "message_len": len(message),
                **trace.as_log_fields(),
            },
        )

        return {"response": response}

    except UpstreamLLMError:
        logger.warning("chat_llm_failure")
        raise HTTPException(status_code=502, detail="LLM failure")

    except DatabaseError:
        logger.error("chat_db_failure")
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    try:
        trace = await get_trace(run_id)
    except DatabaseError:
        logger.error("trace_db_failure")
        raise HTTPException(status_code=503, detail="Database unavailable")

    if trace is None:
        raise HTTPException(status_code=404, detail="run not found")
    return trace


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    try:
        await ping_db()
    except DatabaseError:
        logger.error("ready_db_failure")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok"}
