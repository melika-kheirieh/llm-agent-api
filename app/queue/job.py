from dataclasses import dataclass
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentJob:
    job_id: str
    payload: dict
    status: JobStatus = JobStatus.QUEUED
