from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any


class TraceEventName(str, Enum):
    RUN_STARTED = "run_started"
    ROUTE_SELECTED = "route_selected"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    VERIFICATION_COMPLETED = "verification_completed"
    RECOVERY_DECISION = "recovery_decision"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True)
class TraceEvent:
    name: str
    order: int
    timestamp: float = field(default_factory=time)
    metadata: dict[str, Any] = field(default_factory=dict)


def append_event(
    events: tuple[TraceEvent, ...],
    name: TraceEventName | str,
    **metadata: Any,
) -> tuple[TraceEvent, ...]:
    """Append one observability event. Does not interpret control-loop outcomes."""
    value = name.value if isinstance(name, TraceEventName) else name
    payload = {key: item for key, item in metadata.items() if item is not None}
    return events + (
        TraceEvent(
            name=value,
            order=len(events),
            timestamp=time(),
            metadata=payload,
        ),
    )


def event_names(events: tuple[TraceEvent, ...]) -> tuple[str, ...]:
    return tuple(event.name for event in events)
