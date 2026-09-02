class UpstreamLLMError(Exception):
    """Raised when LLM provider fails"""

class DatabaseError(Exception):
    """Raised when DB operations fail"""


class ConfigurationError(Exception):
    """Raised when application settings are invalid."""
