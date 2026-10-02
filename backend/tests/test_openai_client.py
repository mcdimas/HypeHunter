import io
import json
from urllib.error import HTTPError, URLError

import pytest

from app import openai_client
from app.config import Settings
from app.translation import translation_schema


def settings(**kw):
    return Settings(openai_api_key="test-secret-not-real", openai_enabled=True, **kw)


def mock_response(monkeypatch, value):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if isinstance(value, Exception):
                raise value
            return io.BytesIO(value if isinstance(value, bytes) else json.dumps(value).encode())
    monkeypatch.setattr(openai_client, "build_opener", lambda *_: Opener())
    return calls


def completed(content=None):
    return {"status": "completed", "id": "resp_test", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": content or [{"type": "output_text", "text": '{"translations":[]}'}]}],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "private": "do not persist"}}


def test_responses_contract_and_usage(monkeypatch):
    calls = mock_response(monkeypatch, completed())
    result = openai_client.run_openai("source", translation_schema(), settings())
    request, timeout = calls[0]
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert request.get_header("Authorization") == "Bearer test-secret-not-real"
    body = json.loads(request.data)
    assert body["store"] is False
    assert body["model"] == "gpt-5.6-luna"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"] == translation_schema()
    assert body["max_output_tokens"] == 16000
    assert "tools" not in body
    assert body["reasoning"] == {"effort": "high"}
    assert timeout == 180
    assert result.response_id == "resp_test"
    assert result.usage == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert json.loads(result.response) == {"translations": []}


def test_yandex_contract_no_openai_fallback(monkeypatch):
    calls = mock_response(monkeypatch, completed())
    config = Settings(ai_provider="yandex", yandex_ai_enabled=True, yandex_ai_api_key="synthetic-key",
                      yandex_ai_folder_id="synthetic-folder", openai_enabled=False)
    result = openai_client.run_ai("source", translation_schema(), config)
    request = calls[0][0]
    body = json.loads(request.data)
    assert request.full_url == "https://ai.api.cloud.yandex.net/v1/responses"
    assert request.get_header("Authorization") == "Api-Key synthetic-key"
    assert request.get_header("X-data-logging-enabled") == "false"
    assert body["model"] == "gpt://synthetic-folder/yandexgpt-5.1"
    assert "reasoning" not in body and body["store"] is False
    assert result.response_id == "resp_test"
    config.yandex_ai_enabled = False
    config.openai_enabled = True
    with pytest.raises(RuntimeError):
        openai_client.run_ai("source", translation_schema(), config)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_http_errors_are_safe_and_not_retried(monkeypatch, status):
    error = HTTPError("https://api.openai.com/v1/responses", status, "sensitive provider error", {}, io.BytesIO(b"test-secret-not-real"))
    calls = mock_response(monkeypatch, error)
    with pytest.raises(RuntimeError) as caught:
        openai_client.run_openai("private source", translation_schema(), settings())
    assert "test-secret" not in str(caught.value)
    assert "private" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "output": []},
    completed([{"type": "refusal", "refusal": "private"}]),
    {"status": "completed", "output": []},
    b"not json", b"x" * 1048577, [],
], ids=["incomplete", "refused", "empty", "invalid-json", "oversized", "wrong-type"])
def test_incomplete_refused_invalid_or_oversized_not_success(monkeypatch, payload):
    mock_response(monkeypatch, payload)
    with pytest.raises(ValueError):
        openai_client.run_openai("source", translation_schema(), settings())


def test_timeout_and_missing_configuration(monkeypatch):
    calls = mock_response(monkeypatch, URLError("private details"))
    with pytest.raises(RuntimeError):
        openai_client.run_openai("source", translation_schema(), settings())
    assert len(calls) == 1
    for config in [Settings(), Settings(openai_enabled=True), Settings(openai_api_key="test")]:
        assert not openai_client.translation_ready(config)
        with pytest.raises(RuntimeError):
            openai_client.run_openai("source", translation_schema(), config)
    assert len(calls) == 1
    assert "test-secret-not-real" not in repr(settings())


def test_input_limit_and_redirect_block(monkeypatch):
    calls = mock_response(monkeypatch, completed())
    with pytest.raises(ValueError):
        openai_client.run_openai("x"*1001, translation_schema(), settings(openai_max_input_chars=1000))
    assert not calls
    assert openai_client.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example") is None
