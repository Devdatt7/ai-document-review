"""The ONLY file that talks to an LLM. The rest of the app calls ask_llm / ask_llm_json.

To swap model or provider later, change this file and .env only.
Privacy: never log or print prompts, responses or the API key.
"""

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
DEFAULT_TIMEOUT_SECONDS = 60
TEMPERATURE = 0

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Any LLM problem, with a message that is safe to show to a beginner."""


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    """The single shared client, created on first use."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise LLMError(
            "GEMINI_API_KEY is missing. Copy .env.example to .env and paste your key "
            "(free key: https://aistudio.google.com/apikey)."
        )
    timeout_ms = int(os.getenv("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)) * 1000
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))


def _model() -> str:
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL


def _generate(prompt: str, **config) -> str:
    try:
        response = _client().models.generate_content(
            model=_model(),
            contents=prompt,
            config=types.GenerateContentConfig(temperature=TEMPERATURE, **config),
        )
    except LLMError:
        raise
    except errors.APIError as e:
        if e.code == 429:
            raise LLMError(
                "Gemini rate limit reached (free tier is limited). Wait a minute and try again."
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


def ask_llm(prompt: str) -> str:
    """Send a prompt, get plain text back."""
    return _generate(prompt)


def ask_llm_json(prompt: str, schema: type[T]) -> T:
    """Send a prompt, get back a validated instance of the Pydantic class `schema`."""
    text = _generate(prompt, response_mime_type="application/json", response_schema=schema)
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        raise LLMError("Gemini answered, but not in the expected JSON format. Try again.") from None
