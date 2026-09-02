from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    RETRYING = "retrying"
    FAILED = "failed"


class QueueJob:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = JobStatus.QUEUED
