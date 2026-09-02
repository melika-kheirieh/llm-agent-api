from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.infra.config import ROUTER_MODE_KEYWORD, ROUTER_MODE_LLM, Settings
from app.infra.errors import ConfigurationError
from app.main import create_app


def test_blank_database_url_is_rejected():
    settings = Settings(database_url="  ", llm_timeout_seconds="60")

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        settings.validate_startup()


def test_invalid_provider_is_rejected():
    settings = Settings(llm_provider="claude", llm_timeout_seconds="60")

    with pytest.raises(ConfigurationError, match="Unsupported LLM_PROVIDER"):
        settings.validate_startup()


def test_invalid_timeout_is_rejected():
    settings = Settings(llm_timeout_seconds="fast")

    with pytest.raises(ConfigurationError, match="LLM_TIMEOUT_SECONDS"):
        settings.validate_startup()


def test_non_positive_timeout_is_rejected():
    settings = Settings(llm_timeout_seconds="0")

    with pytest.raises(ConfigurationError, match="LLM_TIMEOUT_SECONDS"):
        settings.validate_startup()


def test_missing_openai_key_is_rejected():
    settings = Settings(
        llm_provider="openai",
        openai_api_key=None,
        llm_timeout_seconds="30",
        router_mode=ROUTER_MODE_KEYWORD,
    )

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        settings.validate_startup()


def test_blank_openai_key_is_rejected():
    settings = Settings(
        llm_provider="openai",
        openai_api_key="  ",
        llm_timeout_seconds="30",
        router_mode=ROUTER_MODE_KEYWORD,
    )

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        settings.validate_startup()


def test_valid_ollama_configuration_starts():
    settings = Settings(
        llm_provider="Ollama",
        llm_timeout_seconds="15",
        router_mode=ROUTER_MODE_KEYWORD,
    )
    settings.validate_startup()

    assert settings.llm_provider == "ollama"
    assert settings.llm_timeout_seconds == 15.0
    assert settings.router_mode == ROUTER_MODE_KEYWORD


def test_valid_openai_configuration_starts():
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-test",
        llm_timeout_seconds="10",
        router_mode=ROUTER_MODE_KEYWORD,
    )
    settings.validate_startup()

    assert settings.llm_provider == "openai"
    assert settings.llm_timeout_seconds == 10.0


def test_invalid_router_mode_is_rejected():
    settings = Settings(router_mode="graph", llm_timeout_seconds="60")

    with pytest.raises(ConfigurationError, match="Unsupported ROUTER_MODE"):
        settings.validate_startup()


def test_llm_router_mode_is_accepted():
    settings = Settings(router_mode="LLM", llm_timeout_seconds="60")
    settings.validate_startup()

    assert settings.router_mode == ROUTER_MODE_LLM


def test_keyword_router_mode_is_the_documented_default():
    settings = Settings(router_mode="Keyword", llm_timeout_seconds="60")
    settings.validate_startup()

    assert settings.router_mode == ROUTER_MODE_KEYWORD


def test_lifespan_validates_before_db_and_runtime(mocker):
    bad_settings = mocker.Mock()
    bad_settings.validate_startup.side_effect = ConfigurationError("bad config")
    mocker.patch("app.main.settings", bad_settings)
    init_db = mocker.patch("app.main.init_db", new_callable=AsyncMock)
    init_runtime = mocker.patch("app.main.init_runtime", new_callable=AsyncMock)
    close_db = mocker.patch("app.main.close_db", new_callable=AsyncMock)
    close_runtime = mocker.patch("app.main.close_runtime", new_callable=AsyncMock)

    with pytest.raises(ConfigurationError, match="bad config"):
        with TestClient(create_app()):
            pass

    init_db.assert_not_called()
    init_runtime.assert_not_called()
    close_db.assert_not_called()
    close_runtime.assert_not_called()


def test_valid_configuration_still_starts_normally(client):
    resp = client.post("/chat", json={"message": "   "})
    assert resp.status_code == 400
