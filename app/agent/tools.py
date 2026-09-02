from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolResult:
    success: bool
    data: dict


class AgentTool(Protocol):
    name: str

    def execute(self, arguments: dict) -> ToolResult: ...
