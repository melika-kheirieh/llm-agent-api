from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any

_ALLOWED_EVENT_METADATA_KEYS = frozenset(
    {
        "router_type",
        "action",
        "tool_name",
        "status",
        "failure_class",
        "attempt",
        "error",
        "verified",
    }
)
_BLOCKED_EVENT_METADATA_KEYS = frozenset(
    {
        "tenant_id",
        "property_id",
        "trusted_scope",
        "data",
        "payload",
        "arguments",
        "message",
        "prompt",
        "response",
        "observations",
        "evidence",
    }
)


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


def sanitize_event_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Copy operator-safe event fields. Drops scope, payloads, and unknown keys.

    In-memory TraceEvent metadata is a debug surface. Persisted rows and
    GET /runs must not carry tenant/property or untrusted tool data.
    """
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in _BLOCKED_EVENT_METADATA_KEYS:
            continue
        if key not in _ALLOWED_EVENT_METADATA_KEYS:
            continue
        if not _is_persistable_scalar(value):
            continue
        safe[key] = value
    return safe


def persisted_event_payload(event: TraceEvent) -> dict[str, Any]:
    return {
        "order": event.order,
        "name": event.name,
        "timestamp": event.timestamp,
        "metadata": sanitize_event_metadata(event.metadata),
    }


def _is_persistable_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
