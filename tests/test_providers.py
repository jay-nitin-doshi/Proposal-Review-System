from unittest.mock import Mock, patch

import pytest
import requests

from src.providers import ProviderValidationError, list_available_models


@pytest.mark.parametrize(
    ("provider", "payload", "expected"),
    [
        (
            "OpenAI",
            {
                "data": [
                    {"id": "gpt-4o-mini"},
                    {"id": "text-embedding-3-large"},
                    {"id": "gpt-4o-realtime-preview"},
                ]
            },
            ["gpt-4o-mini"],
        ),
        (
            "Google Gemini",
            {
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embedding-001",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
            ["gemini-2.5-flash"],
        ),
        (
            "Anthropic",
            {"data": [{"id": "claude-sonnet-4-20250514"}]},
            ["claude-sonnet-4-20250514"],
        ),
    ],
)
def test_list_available_models_validates_and_filters_provider_response(
    provider, payload, expected
):
    response = Mock(ok=True, status_code=200)
    response.json.return_value = payload
    with patch("src.providers.requests.get", return_value=response) as get:
        models = list_available_models(provider, "secret-key")

    assert models == expected
    assert get.call_args.kwargs["timeout"] == 20
    if provider == "Anthropic":
        assert get.call_args.kwargs["headers"]["x-api-key"] == "secret-key"
    elif provider == "Google Gemini":
        assert get.call_args.kwargs["params"]["key"] == "secret-key"
    else:
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-key"


def test_provider_key_rejection_returns_sanitized_error():
    response = Mock(ok=False, status_code=401)
    with patch("src.providers.requests.get", return_value=response):
        with pytest.raises(ProviderValidationError, match="rejected this API key"):
            list_available_models("OpenAI", "not-a-valid-key")


def test_provider_network_error_does_not_echo_request_credentials():
    with patch(
        "src.providers.requests.get",
        side_effect=requests.ConnectionError("request failed with secret-key"),
    ):
        with pytest.raises(ProviderValidationError) as error:
            list_available_models("Google Gemini", "secret-key")

    assert "secret-key" not in str(error.value)


def test_empty_provider_key_is_rejected_without_network_request():
    with patch("src.providers.requests.get") as get:
        with pytest.raises(ProviderValidationError, match="Enter an API key"):
            list_available_models("Anthropic", " ")
    get.assert_not_called()
