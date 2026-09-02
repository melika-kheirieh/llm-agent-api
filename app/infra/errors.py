from enum import Enum


class FailureClass(str, Enum):
    MODEL_TIMEOUT = "model_timeout"
    TOOL_TIMEOUT = "tool_timeout"
    MODEL_ERROR = "model_error"
    TOOL_ERROR = "tool_error"
    VERIFICATION_FAILURE = "verification_failure"
    PERSISTENCE_FAILURE = "persistence_failure"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class AgentFailure(Exception):
    """Typed runtime failure. CancelledError is never wrapped as this type."""

    def __init__(
        self,
        failure_class: FailureClass,
        message: str = "",
        state: object | None = None,
    ):
        self.failure_class = failure_class
        self.state = state
        super().__init__(message or failure_class.value)


class ModelTimeout(AgentFailure):
    def __init__(self, message: str = "Model request timed out", state: object | None = None):
        super().__init__(FailureClass.MODEL_TIMEOUT, message, state)


class ToolTimeout(AgentFailure):
    def __init__(self, message: str = "Tool execution timed out", state: object | None = None):
        super().__init__(FailureClass.TOOL_TIMEOUT, message, state)


class ModelError(AgentFailure):
    def __init__(self, message: str = "Model provider failed", state: object | None = None):
        super().__init__(FailureClass.MODEL_ERROR, message, state)


class ToolError(AgentFailure):
    def __init__(self, message: str = "Tool execution failed", state: object | None = None):
        super().__init__(FailureClass.TOOL_ERROR, message, state)


class UnknownFailure(AgentFailure):
    def __init__(self, message: str = "Unknown failure", state: object | None = None):
        super().__init__(FailureClass.UNKNOWN, message, state)


UpstreamLLMError = ModelError


class DatabaseError(AgentFailure):
    def __init__(self, message: str = "Database unavailable"):
        super().__init__(FailureClass.PERSISTENCE_FAILURE, message)


class ConfigurationError(Exception):
    """Raised when application settings are invalid."""
