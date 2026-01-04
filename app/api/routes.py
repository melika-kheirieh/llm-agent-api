from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.agent.agent import Agent
from app.infra.container import get_agent
from app.infra.errors import UpstreamLLMError, DatabaseError
from app.db.repo import save_chat
import logging


router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat(
    payload: ChatRequest,
    agent: Agent = Depends(get_agent),
) -> dict:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        response = agent.run(message)
        save_chat(message, response)

        logger.info(
            "chat_success",
            extra={"message_len": len(message)},
        )

        return {"response": response}

    except UpstreamLLMError:
        logger.warning("chat_llm_failure")
        raise HTTPException(status_code=502, detail="LLM failure")

    except DatabaseError:
        logger.error("chat_db_failure")
        raise HTTPException(status_code=503, detail="Database unavailable")
