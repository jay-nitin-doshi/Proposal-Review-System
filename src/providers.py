"""Provider API-key validation and available chat-model discovery."""

from __future__ import annotations

from typing import Any

import requests


PROVIDERS = ("OpenAI", "Google Gemini", "Anthropic")

_MODEL_ENDPOINTS = {
    "OpenAI": "https://api.openai.com/v1/models",
    "Google Gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "Anthropic": "https://api.anthropic.com/v1/models",
}


class ProviderValidationError(ValueError):
    """Raised when a provider key cannot be authenticated or model data read."""


def _request_models(provider: str, api_key: str) -> dict[str, Any]:
    if provider not in _MODEL_ENDPOINTS:
        raise ProviderValidationError("Choose a supported AI provider.")
    if not api_key.strip():
        raise ProviderValidationError("Enter an API key.")

    url = _MODEL_ENDPOINTS[provider]
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    if provider == "Google Gemini":
        params["key"] = api_key.strip()
    elif provider == "Anthropic":
        headers = {
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
        }
    else:
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException as exc:
        raise ProviderValidationError(
            "Could not reach the provider API. Check your network and try again."
        ) from exc

    if response.status_code in {401, 403}:
        raise ProviderValidationError("The provider rejected this API key.")
    if not response.ok:
        raise ProviderValidationError(
            f"The provider model-list request failed (HTTP {response.status_code})."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderValidationError(
            "The provider returned an unreadable model list."
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderValidationError("The provider returned an invalid model list.")
    return payload


def list_available_models(provider: str, api_key: str) -> list[str]:
    """Validate a key and return models suitable for chat-based scorecards."""
    payload = _request_models(provider, api_key)
    models: set[str] = set()

    if provider == "OpenAI":
        entries = payload.get("data", [])
        if isinstance(entries, list):
            models = {
                item["id"]
                for item in entries
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and item["id"].startswith(("gpt-", "ft:gpt-"))
                and not any(
                    excluded in item["id"].casefold()
                    for excluded in (
                        "embedding",
                        "realtime",
                        "audio",
                        "transcribe",
                        "tts",
                        "image",
                        "search",
                    )
                )
            }
    elif provider == "Google Gemini":
        entries = payload.get("models", [])
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                methods = item.get("supportedGenerationMethods", [])
                if (
                    isinstance(name, str)
                    and name.startswith("models/")
                    and isinstance(methods, list)
                    and "generateContent" in methods
                ):
                    models.add(name.removeprefix("models/"))
    else:
        entries = payload.get("data", [])
        if isinstance(entries, list):
            models = {
                item["id"]
                for item in entries
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }

    if not models:
        raise ProviderValidationError(
            "The key was accepted, but no supported chat models were returned."
        )
    return sorted(models, key=str.casefold)
