from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentAction(str, Enum):
    DIRECT = "direct"
    USE_TOOL = "use_tool"


@dataclass(frozen=True)
class AgentRequest:
    message: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AgentDecision:
    action: AgentAction
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
