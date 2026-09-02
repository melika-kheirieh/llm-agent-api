from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agent.contracts import AgentAction


class Analysis(BaseModel):
    language: str
    tone: str
    task_type: str


class RoutingOutput(BaseModel):
    """Structured LLM routing payload. Validated before it becomes AgentDecision."""

    model_config = ConfigDict(extra="forbid")

    action: AgentAction
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
