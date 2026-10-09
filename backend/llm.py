"""The ONLY file that talks to an LLM. The rest of the app calls ask_llm / ask_llm_json.

To swap model or provider later, change this file and .env only.
Privacy: never log or print prompts, responses or the API key.
"""

import json
import os
from functools import lru_cache
from typing import TypeVar

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

load_dotenv()

DEFAULT_MODEL = "gemini-3.7-flash"
DEFAULT_FALLBACK_MODELS = "gemini-3.7-flash-lite"
DEFAULT_TIMEOUT_SECONDS = 60
TEMPERATURE = 0

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Any LLM problem, with a message that is safe to show to a beginner."""


class LLMOutputError(LLMError):
    """The model answered, but its output did not match the expected format."""


class LLMRateLimitError(LLMError):
    """The provider rejected a request because a rate or usage limit was reached."""


def _api_keys() -> list[str]:
    """Keys from GEMINI_API_KEYS (comma separated) and GEMINI_API_KEY, de-duplicated, in order."""
    raw = f"{os.getenv('GEMINI_API_KEYS', '')},{os.getenv('GEMINI_API_KEY', '')}"
    keys: list[str] = []
    for key in (part.strip() for part in raw.split(",")):
        if key and key not in keys:
            keys.append(key)
    if not keys:
        raise LLMError(
            "No Gemini key found. Copy .env.example to .env and set GEMINI_API_KEY, or several "
            "keys in GEMINI_API_KEYS separated by commas (free key: https://aistudio.google.com/apikey)."
        )
    return keys


@lru_cache(maxsize=None)
def _client_for(api_key: str) -> genai.Client:
    timeout_ms = int(os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)) * 1000
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))


# Index of the key to try first; moves forward when a key hits its limit so later calls skip it.
_active_key = 0


def _model() -> str:
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL


def _models() -> list[str]:
    """Main model first, then fallbacks (each model has its own free quota)."""
    fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS)
    models: list[str] = []
    for name in [_model(), *(part.strip() for part in fallbacks.split(","))]:
        if name and name not in models:
            models.append(name)
    return models


def _generate_content(prompt: str, **config):
    """Call Gemini: try every key on a model, then move to the next model if all are limited."""
    global _active_key
    keys = _api_keys()
    last_error: errors.APIError | None = None
    for model in _models():
        start = _active_key % len(keys)
        for offset in range(len(keys)):
            index = (start + offset) % len(keys)
            try:
                response = _client_for(keys[index]).models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=TEMPERATURE, **config),
                )
            except errors.APIError as e:
                if e.code in (401, 403, 429):
                    last_error = e
                    _active_key = (index + 1) % len(keys)
                    continue
                raise
            _active_key = index
            return response
    assert last_error is not None
    raise last_error


def _generate_gemini(prompt: str, **config) -> str:
    try:
        response = _generate_content(prompt, **config)
    except LLMError:
        raise
    except errors.APIError as e:
        if e.code == 429:
            raise LLMRateLimitError(
                "Gemini's rate or usage limit was reached on every configured key. Limits depend on "
                "your model and plan; wait for the quota to reset, add another key to "
                "GEMINI_API_KEYS, or check your Google AI Studio usage and billing."
            ) from None
        if e.code in (400, 401, 403):
            raise LLMError(
                f"Gemini rejected the request (HTTP {e.code}). Check GEMINI_API_KEY and "
                f"GEMINI_MODEL ('{_model()}') in .env."
            ) from None
        if e.code == 404:
            raise LLMError(f"Gemini model '{_model()}' was not found. Check GEMINI_MODEL in .env.") from None
        raise LLMError(f"Gemini API error (HTTP {e.code}). Try again in a moment.") from None
    except httpx.TimeoutException:
        raise LLMError("Gemini took too long to answer (timeout). Try again.") from None
    except httpx.RequestError:
        raise LLMError("Could not reach Gemini. Check your internet connection.") from None

    if not response.text:
        raise LLMError("Gemini returned an empty answer (it may have been blocked). Try again.")
    return response.text


XAI_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-3-mini"


def _xai_key() -> str:
    return os.getenv("XAI_API_KEY", "").strip()


def _generate_xai(prompt: str, **config) -> str:
    """Backup provider (xAI Grok, OpenAI-compatible API). Used only after Gemini is unavailable."""
    content = prompt
    body: dict = {"model": os.getenv("XAI_MODEL") or DEFAULT_XAI_MODEL, "temperature": TEMPERATURE}
    schema = config.get("response_schema")
    if schema is not None:
        body["response_format"] = {"type": "json_object"}
        content = (
            f"{prompt}\n\nReturn ONLY a JSON object that matches this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
    body["messages"] = [{"role": "user", "content": content}]
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    try:
        response = httpx.post(
            XAI_URL, json=body, timeout=timeout, headers={"Authorization": f"Bearer {_xai_key()}"}
        )
    except httpx.TimeoutException:
        raise LLMError("The backup provider (xAI) took too long to answer. Try again.") from None
    except httpx.RequestError:
        raise LLMError("Could not reach the backup provider (xAI). Check your internet connection.") from None
    if response.status_code == 429:
        raise LLMRateLimitError("The xAI backup key has also reached its rate or usage limit.")
    if response.status_code != 200:
        raise LLMError(
            f"xAI rejected the request (HTTP {response.status_code}). Check XAI_API_KEY and XAI_MODEL in .env."
        )
    try:
        text = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        text = ""
    if not text:
        raise LLMError("xAI returned an empty answer. Try again.")
    return text


def _generate(prompt: str, **config) -> str:
    """Gemini first (all keys); xAI only if Gemini is rate limited or has no key configured."""
    try:
        return _generate_gemini(prompt, **config)
    except LLMRateLimitError:
        if not _xai_key():
            raise
    except LLMError:
        if not _xai_key() or _gemini_configured():
            raise
    return _generate_xai(prompt, **config)


def _gemini_configured() -> bool:
    try:
        return bool(_api_keys())
    except LLMError:
        return False

def ask_llm(prompt: str) -> str:
    """Send a prompt, get plain text back."""
    return _generate(prompt)


def ask_llm_json(prompt: str, schema: type[T]) -> T:
    """Send a prompt, get back a validated instance of the Pydantic class `schema`."""
    text = _generate(prompt, response_mime_type="application/json", response_schema=schema)
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        raise LLMOutputError(
            "Gemini answered, but not in the expected JSON format. Try again."
        ) from None
