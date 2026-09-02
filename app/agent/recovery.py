from enum import Enum


class RecoveryAction(str, Enum):
    RETRY = "retry"
    ESCALATE = "escalate"
    FAIL = "fail"


class RecoveryPolicy:
    def __init__(self, max_attempts: int = 1):
        self.max_attempts = max_attempts

    def decide(self, attempt: int, retryable: bool) -> RecoveryAction:
        if retryable and attempt < self.max_attempts:
            return RecoveryAction.RETRY
        if retryable:
            return RecoveryAction.ESCALATE
        return RecoveryAction.FAIL
