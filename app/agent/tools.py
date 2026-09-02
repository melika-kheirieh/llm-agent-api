from dataclasses import dataclass
from typing import Protocol

from app.agent.context import TrustedScope


@dataclass(frozen=True)
class ToolResult:
    success: bool
    data: dict
    retryable: bool = False


class AgentTool(Protocol):
    """Async tool. TrustedScope is never part of model-generated arguments."""

    name: str

    async def execute(
        self,
        arguments: dict,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult: ...
