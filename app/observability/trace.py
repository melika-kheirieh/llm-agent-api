from dataclasses import dataclass, field
from time import time


@dataclass
class TraceEvent:
    name: str
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time)
