from dataclasses import dataclass


@dataclass
class JobMessage:
    job_id: str
    payload: dict


class Worker:
    def process(self, message: JobMessage) -> str:
        return message.job_id
