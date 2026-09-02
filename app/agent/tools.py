from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolResult:
    success: bool
    data: dict


class AgentTool(Protocol):
    name: str

    async def execute(self, arguments: dict) -> ToolResult: ...
