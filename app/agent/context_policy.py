from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPolicy:
    """Controls which context can be passed into agent execution."""

    max_history_items: int = 5

    def filter_history(self, items: list[str]) -> list[str]:
        return items[-self.max_history_items :]
