from dataclasses import dataclass


@dataclass
class AgentMetrics:
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0

    def record_success(self):
        self.success_count += 1

    def record_failure(self):
        self.failure_count += 1
