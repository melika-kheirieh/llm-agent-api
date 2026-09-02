from dataclasses import dataclass
from typing import Dict


@dataclass
class ContextCheckpoint:
    thread_id: str
    state: Dict[str, object]


class CheckpointStore:
    def __init__(self) -> None:
        self._items: Dict[str, ContextCheckpoint] = {}

    def save(self, checkpoint: ContextCheckpoint) -> None:
        self._items[checkpoint.thread_id] = checkpoint

    def load(self, thread_id: str) -> ContextCheckpoint | None:
        return self._items.get(thread_id)
