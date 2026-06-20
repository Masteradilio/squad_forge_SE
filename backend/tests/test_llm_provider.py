from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from localforge.llm import (
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    OpenAICompatibleProvider,
    chat_completion_validated,
    clean_json_str,
)
from localforge.llm.fake import FakeLLMProvider
from pydantic import BaseModel, Field


# Pydantic test models
class SimpleResponse(BaseModel):
    name: str
    attempts: int = Field(default=1)


class NestedResponse(BaseModel):
    title: str
    items: list[str]


def test_clean_json_str():
    """Verify that clean_json_str extracts raw JSON strings from markdown fences."""
    raw1 = "```json\n{\n  \"name\": \"test\"\n}\n```"
    assert clean_json_str(raw1) == "{\n  \"name\": \"test\"\n}"

    raw2 = "  ```\n{\n  \"name\": \"test\"\n}\n```  "
    assert clean_json_str(raw2) == "{\n  \"name\": \"test\"\n}"

    raw3 = "{\n  \"name\": \"test\"\n}"
    assert clean_json_str(raw3) == "{\n  \"name\": \"test\"\n}"


@pytest.mark.anyio
async def test_openai_compatible_provider_list_models():
    """Verify list_models maps API values successfully."""
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"id": "llama3"}, {"id": "mistral"}]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        models = await provider.list_models()
        assert models == ["llama3", "mistral"]


@pytest.mark.anyio
async def test_openai_compatible_provider_chat_success():
    """Verify chat completions fetch model response content."""
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1", default_model="llama3"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Mocked LLM answer."}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.chat_completion([{"role": "user", "content": "hello"}])
        assert res == "Mocked LLM answer."
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "llama3"
        assert kwargs["json"]["stream"] is False


@pytest.mark.anyio
async def test_openai_compatible_provider_failures():
    """Verify that httpx timeouts and connection errors raise mapped exceptions."""
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1", default_model="llama3"
    )

    # 1. Timeout
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(LLMTimeoutError):
            await provider.chat_completion([{"role": "user", "content": "hello"}])

    # 2. Connection failure
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection failed")):
        with pytest.raises(LLMConnectionError):
            await provider.chat_completion([{"role": "user", "content": "hello"}])

    # 3. HTTP status error
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 500
    mock_err_resp.text = "Internal Server Error"
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_err_resp
        with pytest.raises(LLMError) as exc:
            await provider.chat_completion([{"role": "user", "content": "hello"}])
        assert "500" in str(exc.value)


@pytest.mark.anyio
async def test_openai_compatible_provider_stream():
    """Verify that streaming chat completion yields delta content."""
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1", default_model="llama3"
    )

    # We mock the response of AsyncClient.stream context manager
    class MockStreamResponse:
        def __init__(self, status_code: int = 200):
            self.status_code = status_code

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aread(self):
            return b"error details"

        async def aiter_lines(self):
            lines = [
                'data: {"choices": [{"delta": {"content": "Hello"}}]}',
                'data: {"choices": [{"delta": {"content": " world"}}]}',
                "data: [DONE]",
            ]
            for line in lines:
                yield line

    with patch("httpx.AsyncClient.stream", return_value=MockStreamResponse()):
        stream_iter = await provider.chat_completion(
            [{"role": "user", "content": "hello"}], stream=True
        )
        assert not isinstance(stream_iter, str)

        chunks = []
        async for chunk in stream_iter:
            chunks.append(chunk)

        assert chunks == ["Hello", " world"]


@pytest.mark.anyio
async def test_chat_completion_validated_success():
    """Verify that chat_completion_validated returns a validated Pydantic model."""
    mock_responses = ['{"name": "Valid Output", "attempts": 1}']
    fake_provider = FakeLLMProvider(responses=mock_responses)

    result = await chat_completion_validated(
        provider=fake_provider,
        messages=[{"role": "user", "content": "test"}],
        schema_model=SimpleResponse,
    )

    assert isinstance(result, SimpleResponse)
    assert result.name == "Valid Output"
    assert result.attempts == 1


@pytest.mark.anyio
async def test_chat_completion_validated_repair_success():
    """Verify that a parsing failure triggers a repair prompt and succeeds on the second try."""
    mock_responses = [
        "This is not a JSON string, sorry!",
        '{"name": "Repaired Output", "attempts": 2}',
    ]
    fake_provider = FakeLLMProvider(responses=mock_responses)
    messages = [{"role": "user", "content": "request schema"}]

    result = await chat_completion_validated(
        provider=fake_provider,
        messages=messages,
        schema_model=SimpleResponse,
        max_retries=1,
    )

    assert isinstance(result, SimpleResponse)
    assert result.name == "Repaired Output"
    assert result.attempts == 2

    # Check payload log context: last payload should have appended assistant's bad reply
    # and user's correction prompt.
    last_payload_messages = fake_provider.last_payload["messages"]
    assert len(last_payload_messages) == 3
    assert last_payload_messages[0]["content"] == "request schema"
    assert last_payload_messages[1]["role"] == "assistant"
    assert last_payload_messages[1]["content"] == "This is not a JSON string, sorry!"
    assert last_payload_messages[2]["role"] == "user"
    assert "JSON formatting error" in last_payload_messages[2]["content"]


@pytest.mark.anyio
async def test_chat_completion_validated_failed_exhausted():
    """Verify that validation fails permanently if repair attempts are exhausted."""
    mock_responses = [
        '{"name": 1234, "attempts": "should-be-int"}',  # Schema Validation error
        '{"name": "Still invalid", "attempts": "bad-type"}',
    ]
    fake_provider = FakeLLMProvider(responses=mock_responses)

    with pytest.raises(ValueError) as exc:
        await chat_completion_validated(
            provider=fake_provider,
            messages=[{"role": "user", "content": "test"}],
            schema_model=SimpleResponse,
            max_retries=1,
        )

    assert "Failed to validate LLM output after 1 retries" in str(exc.value)
