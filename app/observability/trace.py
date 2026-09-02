from dataclasses import dataclass, field
from time import time


@dataclass
class TraceEvent:
    name: str
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time)


@dataclass
class ExecutionTrace:
    run_id: str
    request_id: str
    thread_id: str | None = None
    selected_tool: str | None = None
    verification_result: str | None = None
    retry_count: int = 0
    failure_class: str | None = None
