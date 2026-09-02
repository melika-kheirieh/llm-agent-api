import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pydantic import BaseModel, ConfigDict

from app.infra.errors import ModelError, ModelTimeout, UpstreamLLMError
from app.llm.ollama import OllamaClient
from app.llm.openai import OpenAIClient


class _NameSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


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
    mock_client.aclose = AsyncMock()
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


def test_ollama_timeout_is_model_timeout(mocker):
    _mock_httpx_client(mocker, post_side_effect=httpx.TimeoutException("timed out"))

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")

    with pytest.raises(ModelTimeout, match="timed out"):
        _run(client.generate("hi"))


def test_ollama_http_error(mocker):
    _mock_httpx_client(
        mocker,
        post_side_effect=httpx.ConnectError("connection refused"),
    )

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")

    with pytest.raises(UpstreamLLMError, match="connection refused"):
        _run(client.generate("hi"))


def test_openai_does_not_wrap_cancellation(mocker):
    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(side_effect=asyncio.CancelledError)
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test")

    async def _generate():
        with pytest.raises(asyncio.CancelledError):
            await client.generate("hi")

    _run(_generate())


def test_openai_aclose_closes_client(mocker):
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test")
    _run(client.aclose())

    mock_client.close.assert_awaited_once()


def test_ollama_does_not_wrap_cancellation(mocker):
    _mock_httpx_client(mocker, post_side_effect=asyncio.CancelledError)

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")

    async def _generate():
        with pytest.raises(asyncio.CancelledError):
            await client.generate("hi")

    _run(_generate())


def test_ollama_aclose_closes_httpx_client(mocker):
    mock_client = _mock_httpx_client(mocker)

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")
    _run(client.aclose())

    mock_client.aclose.assert_awaited_once()


def test_openai_generate_structured_success(mocker):
    mock_resp = MagicMock()
    mock_resp.output_text = '{"name": "wo"}'

    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(return_value=mock_resp)
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
    parsed = _run(client.generate_structured("hi", _NameSchema))

    assert parsed.name == "wo"
    mock_client.responses.create.assert_awaited_once_with(
        model="gpt-4o-mini",
        input="hi",
        text={"format": {"type": "json_object"}},
    )


def test_openai_generate_structured_falls_back_when_native_unsupported(mocker):
    fallback = MagicMock()
    fallback.output_text = '{"name": "plain"}'

    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(
        side_effect=[RuntimeError("json_object unsupported"), fallback]
    )
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
    parsed = _run(client.generate_structured("hi", _NameSchema))

    assert parsed.name == "plain"
    assert mock_client.responses.create.await_count == 2
    mock_client.responses.create.assert_awaited_with(
        model="gpt-4o-mini",
        input="hi",
    )


def test_openai_generate_structured_malformed_native_output(mocker):
    mock_resp = MagicMock()
    mock_resp.output_text = "not json"

    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(return_value=mock_resp)
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test")

    with pytest.raises(ModelError, match="Malformed structured output"):
        _run(client.generate_structured("hi", _NameSchema))
    mock_client.responses.create.assert_awaited_once()


def test_openai_generate_structured_timeout_does_not_fallback(mocker):
    mock_client = MagicMock()
    mock_client.responses.create = AsyncMock(side_effect=TimeoutError("timed out"))
    mocker.patch("app.llm.openai.AsyncOpenAI", return_value=mock_client)

    client = OpenAIClient(api_key="sk-test")

    with pytest.raises(ModelTimeout, match="timed out"):
        _run(client.generate_structured("hi", _NameSchema))
    mock_client.responses.create.assert_awaited_once()


def test_ollama_generate_structured_success(mocker):
    response = MagicMock()
    response.json.return_value = {"response": '{"name": "wo"}'}
    response.raise_for_status = MagicMock()
    mock_client = _mock_httpx_client(mocker, post_return=response)

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")
    parsed = _run(client.generate_structured("hi", _NameSchema))

    assert parsed.name == "wo"
    mock_client.post.assert_awaited_once_with(
        "http://localhost:11434/api/generate",
        json={
            "model": "gemma",
            "prompt": "hi",
            "stream": False,
            "format": "json",
        },
    )


def test_ollama_generate_structured_falls_back_on_http_error(mocker):
    fallback = MagicMock()
    fallback.json.return_value = {"response": '{"name": "plain"}'}
    fallback.raise_for_status = MagicMock()
    mock_client = _mock_httpx_client(
        mocker,
        post_side_effect=[
            httpx.ConnectError("connection refused"),
            fallback,
        ],
    )

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")
    parsed = _run(client.generate_structured("hi", _NameSchema))

    assert parsed.name == "plain"
    assert mock_client.post.await_count == 2
    mock_client.post.assert_awaited_with(
        "http://localhost:11434/api/generate",
        json={"model": "gemma", "prompt": "hi", "stream": False},
    )


def test_ollama_generate_structured_malformed_json_does_not_fallback(mocker):
    response = MagicMock()
    response.json.return_value = {"response": "not json"}
    response.raise_for_status = MagicMock()
    mock_client = _mock_httpx_client(mocker, post_return=response)

    client = OllamaClient(base_url="http://localhost:11434", model="gemma")

    with pytest.raises(ModelError, match="Malformed structured output"):
        _run(client.generate_structured("hi", _NameSchema))
    mock_client.post.assert_awaited_once()
