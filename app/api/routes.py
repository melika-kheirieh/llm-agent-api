from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.agent.async_runtime import AsyncAgentRuntime
from app.infra.container import get_agent
from app.infra.errors import UpstreamLLMError, DatabaseError
from app.db.repo import save_chat
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
        await save_chat(message, response)

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
