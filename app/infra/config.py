from pydantic import BaseModel
import math
import os
from dotenv import load_dotenv

from app.infra.errors import ConfigurationError

load_dotenv()

SUPPORTED_PROVIDERS = frozenset({"ollama", "openai"})
ROUTER_MODE_KEYWORD = "keyword"
ROUTER_MODE_LLM = "llm"
SUPPORTED_ROUTER_MODES = frozenset({ROUTER_MODE_KEYWORD, ROUTER_MODE_LLM})


def normalize_router_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    if mode not in SUPPORTED_ROUTER_MODES:
        raise ConfigurationError(
            f"Unsupported ROUTER_MODE: {value!r}. "
            "Expected 'keyword' or 'llm'."
        )
    return mode


class Settings(BaseModel):
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")

    # OpenAI
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")

    # Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma")

    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")
    llm_timeout_seconds: float | str = os.getenv("LLM_TIMEOUT_SECONDS", "60")
    router_mode: str = os.getenv("ROUTER_MODE", ROUTER_MODE_KEYWORD)

    def validate_startup(self) -> None:
        """Fail fast on invalid settings. Safe to call more than once."""
        provider = (self.llm_provider or "").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ConfigurationError(
                f"Unsupported LLM_PROVIDER: {self.llm_provider!r}. "
                "Expected 'ollama' or 'openai'."
            )
        self.llm_provider = provider

        try:
            timeout = float(self.llm_timeout_seconds)
        except (TypeError, ValueError) as e:
            raise ConfigurationError(
                "LLM_TIMEOUT_SECONDS must be a positive number, "
                f"got {self.llm_timeout_seconds!r}."
            ) from e
        if not math.isfinite(timeout) or timeout <= 0:
            raise ConfigurationError(
                "LLM_TIMEOUT_SECONDS must be a positive number, "
                f"got {self.llm_timeout_seconds!r}."
            )
        self.llm_timeout_seconds = timeout
        self.router_mode = normalize_router_mode(self.router_mode)

        if provider == "openai" and not (self.openai_api_key or "").strip():
            raise ConfigurationError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai"
            )


settings = Settings()
