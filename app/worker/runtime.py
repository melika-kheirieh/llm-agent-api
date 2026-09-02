from dataclasses import dataclass


@dataclass
class WorkerResult:
    status: str
    attempts: int = 1


class AsyncWorker:
    def execute(self, job):
        return WorkerResult(status="completed")
