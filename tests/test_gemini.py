import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.genai import errors
from httpx import ReadTimeout

from nyaysaathi.gemini import GeminiProvider
from nyaysaathi.intake import IntakeError
from nyaysaathi.models import CaseFile, IntakeResponse
from nyaysaathi.settings import Settings


def fake_client(monkeypatch):
    client = Mock()
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=client)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("nyaysaathi.gemini.genai.Client", factory)
    return factory, client


def test_real_sdk_request_configuration_with_mocked_transport(monkeypatch):
    factory, client = fake_client(monkeypatch)
    client.models.generate_content.return_value = SimpleNamespace(text='{"mocked": true}')
    provider = GeminiProvider(Settings("test-placeholder", "configured-model"))
    messages = [{"role": "user", "content": "रिफंड चाहिए"}]
    assert provider.analyze(CaseFile(), messages, "hi") == '{"mocked": true}'
    client.models.generate_content.assert_called_once()
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "configured-model"
    assert json.loads(kwargs["contents"])["conversation"] == messages
    assert "verified_sources" in json.loads(kwargs["contents"])
    assert kwargs["config"].response_json_schema == IntakeResponse.model_json_schema()
    http = factory.call_args.kwargs["http_options"]
    assert http.timeout == 45000
    assert http.retry_options.attempts == 1
    assert factory.call_args.kwargs["vertexai"] is False
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("settings", [Settings(), Settings("test-placeholder"), Settings(gemini_model="model")])
def test_missing_configuration_never_constructs_client(settings, monkeypatch):
    factory, _ = fake_client(monkeypatch)
    with pytest.raises(IntakeError, match="missing_configuration"):
        GeminiProvider(settings).analyze(CaseFile(), [], "en")
    factory.assert_not_called()


@pytest.mark.parametrize("error,code", [
    (errors.APIError(429, {"error": {"message": "sensitive-placeholder"}}), "rate_limit"),
    (errors.APIError(403, {"error": {"message": "sensitive-placeholder"}}), "model_error"),
    (errors.APIError(404, {"error": {"message": "sensitive-placeholder"}}), "model_error"),
    (errors.APIError(504, {"error": {"message": "sensitive-placeholder"}}), "timeout"),
    (ReadTimeout("sensitive-placeholder"), "timeout"),
    (RuntimeError("sensitive-placeholder"), "model_error"),
])
def test_provider_errors_are_sanitized_and_not_retried(monkeypatch, error, code):
    _, client = fake_client(monkeypatch)
    client.models.generate_content.side_effect = error
    with pytest.raises(IntakeError) as captured:
        GeminiProvider(Settings("test-placeholder", "model")).analyze(CaseFile(), [], "en")
    assert captured.value.code == code
    assert "sensitive-placeholder" not in str(captured.value)
    client.models.generate_content.assert_called_once()


def test_empty_or_blocked_response_is_handled(monkeypatch):
    _, client = fake_client(monkeypatch)
    client.models.generate_content.return_value = SimpleNamespace(text=None)
    with pytest.raises(IntakeError, match="invalid_output"):
        GeminiProvider(Settings("test-placeholder", "model")).analyze(CaseFile(), [], "en")
