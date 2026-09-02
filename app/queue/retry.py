from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_attempts: int = 3

    def can_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts
