from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextItem:
    key: str
    value: Any
    source: str


class ContextPolicy:
    def select(self, items: list[ContextItem]) -> list[ContextItem]:
        return [item for item in items if item.value is not None]
