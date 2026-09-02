import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.infra.errors import UpstreamLLMError
from app.llm.ollama import OllamaClient
from app.llm.openai import OpenAIClient


def _run(coro):
    return asyncio.run(coro)


def test_openai_generate_success(mocker):
    mock_resp = MagicMock()
    mock_resp.output_text = "hello from openai"

    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(return_value=mock_resp)
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
    text = _run(client.generate("hi"))

    assert text == "hello from openai"
    mock_client.responses.create.assert_awaited_once_with(
        model="gpt-4o-mini",
        input="hi",
    )


def test_openai_empty_response(mocker):
    mock_resp = MagicMock()
    mock_resp.output_text = "   "

    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(return_value=mock_resp)
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test")

    with pytest.raises(UpstreamLLMError, match="Empty response from OpenAI"):
        _run(client.generate("hi"))


def test_openai_sdk_error(mocker):
    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(side_effect=RuntimeError("api down"))
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test")

    with pytest.raises(UpstreamLLMError, match="api down"):
        _run(client.generate("hi"))


def _mock_httpx_client(mocker, *, post_return=None, post_side_effect=None):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=post_return, side_effect=post_side_effect)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mocker.patch("app.llm.ollama.httpx.AsyncClient", return_value=mock_client)
    return mock_client


def test_ollama_generate_success(mocker):
    response = MagicMock()
    response.json.return_value = {"response": "hello from ollama"}
    response.raise_for_status = MagicMock()
    mock_client = _mock_httpx_client(mocker, post_return=response)

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")
    text = _run(client.generate("hi"))

    assert text == "hello from ollama"
    mock_client.post.assert_awaited_once_with(
        "http://localhost:11434/api/generate",
        json={"model": "gemma", "prompt": "hi", "stream": False},
    )


def test_ollama_empty_response(mocker):
    response = MagicMock()
    response.json.return_value = {"response": ""}
    response.raise_for_status = MagicMock()
    _mock_httpx_client(mocker, post_return=response)

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")

    with pytest.raises(UpstreamLLMError, match="Empty response from Ollama"):
        _run(client.generate("hi"))


def test_ollama_http_error(mocker):
    _mock_httpx_client(
        mocker,
        post_side_effect=httpx.ConnectError("connection refused"),
    )

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")

    with pytest.raises(UpstreamLLMError, match="connection refused"):
        _run(client.generate("hi"))
