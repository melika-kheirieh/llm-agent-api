from app.agent.agent import Agent
from app.infra.config import settings


def get_agent() -> Agent:
    provider = settings.llm_provider.lower().strip()

    if provider == "ollama":
        from app.llm.ollama import OllamaClient

        llm = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
        return Agent(llm)

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        from app.llm.openai import OpenAIClient

        llm = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
        return Agent(llm)

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
