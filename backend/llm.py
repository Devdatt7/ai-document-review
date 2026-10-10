"""The ONLY file that talks to an LLM. The rest of the app calls ask_llm / ask_llm_json.

To swap model or provider later, change this file and .env only.
Privacy: never log or print prompts, responses or the API key.
"""

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import TypeVar

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = "gemini-3.7-flash"
DEFAULT_FALLBACK_MODELS = "gemini-3.7-flash-lite"
DEFAULT_TIMEOUT_SECONDS = 60
TEMPERATURE = 0
ANALYSIS_TIMEOUT_SECONDS = 295
_analysis_deadline: ContextVar[float | None] = ContextVar("analysis_deadline", default=None)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Any LLM problem, with a message that is safe to show to a beginner."""


class LLMOutputError(LLMError):
    """The model answered, but its output did not match the expected format."""


class LLMRateLimitError(LLMError):
    """The provider rejected a request because a rate or usage limit was reached."""


class LLMTimeoutError(LLMError):
    """The shared analysis budget has expired."""


def check_analysis_deadline() -> None:
    deadline = _analysis_deadline.get()
    if deadline is not None and monotonic() >= deadline:
        raise LLMTimeoutError(
            "Analysis exceeded its 295-second time budget. No completed report was produced. "
            "Try a shorter document or a specific faster free model."
        )


@contextmanager
def analysis_time_budget():
    token = _analysis_deadline.set(monotonic() + ANALYSIS_TIMEOUT_SECONDS)
    try:
        yield
        check_analysis_deadline()
    finally:
        _analysis_deadline.reset(token)


def _request_timeout() -> float:
    check_analysis_deadline()
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    deadline = _analysis_deadline.get()
    return min(timeout, max(0.001, deadline - monotonic())) if deadline is not None else timeout


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
    timeout_ms = int(_request_timeout() * 1000)
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)
    ))


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
                    config=types.GenerateContentConfig(
                        temperature=TEMPERATURE,
                        http_options=types.HttpOptions(
                            timeout=max(1, int(_request_timeout() * 1000)),
                            retry_options=types.HttpRetryOptions(attempts=1),
                        ),
                        **config,
                    ),
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
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _xai_key() -> str:
    return os.getenv("XAI_API_KEY", "").strip()


def _generate_xai(prompt: str, **config) -> str:
    """Backup provider (xAI Grok, OpenAI-compatible API). Used only after Gemini is unavailable."""
    return _generate_chat(
        prompt, "xAI", XAI_URL, _xai_key(),
        os.getenv("XAI_MODEL") or DEFAULT_XAI_MODEL, **config
    )


def _generate_openai(prompt: str, **config) -> str:
    return _generate_chat(
        prompt, "OpenAI", OPENAI_URL, os.getenv("OPENAI_API_KEY", "").strip(),
        os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL, **config
    )


def _generate_openrouter(prompt: str, **config) -> str:
    model = (os.getenv("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip()
    if model != DEFAULT_OPENROUTER_MODEL and not model.endswith(":free"):
        raise LLMError(
            "OPENROUTER_MODEL must be 'openrouter/free' or a model ID ending in ':free'. "
            "Paid OpenRouter models are not enabled."
        )
    return _generate_chat(
        prompt, "OpenRouter", OPENROUTER_URL,
        os.getenv("OPENROUTER_API_KEY", "").strip(), model, **config
    )


def _generate_chat(
    prompt: str, provider: str, url: str, api_key: str, model: str, **config
) -> str:
    content = prompt
    body: dict = {"model": model, "temperature": TEMPERATURE}
    schema = config.get("response_schema")
    if schema is not None:
        body["response_format"] = {"type": "json_object"}
        content = (
            f"{prompt}\n\nReturn ONLY a JSON object that matches this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
    body["messages"] = [{"role": "user", "content": content}]
    if provider == "OpenRouter":
        body["provider"] = {"require_parameters": True}
    timeout = _request_timeout()
    try:
        response = httpx.post(
            url, json=body, timeout=timeout, headers={"Authorization": "Bearer " + api_key}
        )
    except httpx.TimeoutException:
        raise LLMError(f"The backup provider ({provider}) took too long to answer. Try again.") from None
    except httpx.RequestError:
        raise LLMError(f"Could not reach the backup provider ({provider}). Check your internet connection.") from None
    if response.status_code == 429:
        raise LLMRateLimitError(f"The {provider} backup key has also reached its rate or usage limit.")
    if response.status_code != 200:
        raise LLMError(
            f"{provider} rejected the request (HTTP {response.status_code}). "
            f"Check {provider.upper()}_API_KEY and {provider.upper()}_MODEL in the backend environment."
        )
    try:
        payload = response.json()
        choice = payload["choices"][0]
        text = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMOutputError(f"{provider} returned an invalid response. Try again.") from None
    if provider == "OpenRouter" and choice.get("finish_reason") != "stop":
        raise LLMOutputError("OpenRouter returned an incomplete or blocked answer. Try again.")
    if not isinstance(text, str) or not text.strip():
        raise LLMOutputError(f"{provider} returned an empty or invalid answer. Try again.")
    return text


def _generate_anthropic(prompt: str, **config) -> str:
    body: dict = {
        "model": os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL,
        "max_tokens": 8192,
        "temperature": TEMPERATURE,
        "messages": [{"role": "user", "content": prompt}],
    }
    schema = config.get("response_schema")
    if schema is not None:
        # A forced tool supplies structured data; no external tool is executed.
        body["tools"] = [{
            "name": "review_result",
            "description": "Return the requested result matching the provided schema.",
            "input_schema": schema.model_json_schema(),
        }]
        body["tool_choice"] = {"type": "tool", "name": "review_result"}
    try:
        response = httpx.post(
            ANTHROPIC_URL, json=body,
            timeout=_request_timeout(),
            headers={
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", "").strip(),
                "anthropic-version": "2023-06-01",
            },
        )
    except httpx.TimeoutException:
        raise LLMError("Claude took too long to answer. Try again.") from None
    except httpx.RequestError:
        raise LLMError("Could not reach Claude. Check your internet connection.") from None
    if response.status_code == 429:
        raise LLMRateLimitError("Claude has reached its rate or usage limit.")
    if response.status_code != 200:
        raise LLMError(
            f"Claude rejected the request (HTTP {response.status_code}). "
            "Check ANTHROPIC_API_KEY and ANTHROPIC_MODEL in the backend environment."
        )
    try:
        payload = response.json()
        stop_reason = payload["stop_reason"]
        blocks = payload["content"]
    except (ValueError, KeyError, TypeError):
        raise LLMOutputError("Claude returned an invalid response. Try again.") from None
    if stop_reason == "max_tokens":
        raise LLMOutputError("Claude's answer exceeded the output token limit. Use a shorter document.")
    if not isinstance(blocks, list) or not all(isinstance(block, dict) for block in blocks):
        raise LLMOutputError("Claude returned invalid content blocks. Try again.")
    if schema is not None:
        results = [
            block.get("input") for block in blocks
            if block.get("type") == "tool_use" and block.get("name") == "review_result"
        ]
        if stop_reason != "tool_use" or len(results) != 1 or not isinstance(results[0], dict):
            raise LLMOutputError("Claude did not return the expected structured result. Try again.")
        return json.dumps(results[0])
    texts = [block.get("text") for block in blocks if block.get("type") == "text"]
    if stop_reason != "end_turn" or not texts or not all(
        isinstance(text, str) and text.strip() for text in texts
    ):
        raise LLMOutputError("Claude returned an empty or invalid answer. Try again.")
    return "\n".join(texts)


def _generate(prompt: str, **config) -> str:
    """Gemini, then configured backups; advance only for missing keys or rate limits."""
    check_analysis_deadline()
    backups = [
        generate for key, generate in [
            ("OPENROUTER_API_KEY", _generate_openrouter),
            ("XAI_API_KEY", _generate_xai),
            ("OPENAI_API_KEY", _generate_openai),
            ("ANTHROPIC_API_KEY", _generate_anthropic),
        ] if os.getenv(key, "").strip()
    ]
    if not backups and not _gemini_configured():
        raise LLMError(
            "No AI provider key is configured in the backend. For free OpenRouter analysis, "
            "set OPENROUTER_API_KEY and OPENROUTER_MODEL=openrouter/free in Render's backend "
            "Environment settings, then redeploy. Locally, use the repository-root .env "
            "and restart the backend. Frontend .env.local does not configure the backend."
        )
    try:
        return _generate_gemini(prompt, **config)
    except LLMRateLimitError:
        if not backups:
            raise
    except LLMError:
        if _gemini_configured() or not backups:
            raise
    for index, generate in enumerate(backups):
        check_analysis_deadline()
        try:
            return generate(prompt, **config)
        except LLMRateLimitError:
            if index == len(backups) - 1:
                raise
    raise AssertionError("Configured backup providers were not attempted")


def _gemini_configured() -> bool:
    try:
        return bool(_api_keys())
    except LLMError:
        return False

def ask_llm(prompt: str) -> str:
    """Send a prompt, get plain text back."""
    text = _generate(prompt)
    check_analysis_deadline()
    return text


def ask_llm_json(prompt: str, schema: type[T]) -> T:
    """Send a prompt, get back a validated instance of the Pydantic class `schema`."""
    text = _generate(prompt, response_mime_type="application/json", response_schema=schema)
    check_analysis_deadline()
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        raise LLMOutputError(
            "The AI provider answered, but not in the expected JSON format. Try again."
        ) from None
