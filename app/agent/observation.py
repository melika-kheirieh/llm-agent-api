from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Observation:
    tool_name: str
    success: bool
    data: dict[str, Any]
