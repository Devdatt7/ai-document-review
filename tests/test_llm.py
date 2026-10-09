import os

import pytest

import llm


def _live_gemini_enabled(environ=None):
    """Require an explicit opt-in and a configured key before enabling the live test."""
    environ = os.environ if environ is None else environ
    return environ.get("RUN_LIVE_GEMINI_TEST") == "1" and bool(environ.get("GEMINI_API_KEY"))


def test_live_gemini_requires_explicit_opt_in_even_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("RUN_LIVE_GEMINI_TEST", raising=False)
    assert not _live_gemini_enabled()


def test_live_gemini_requires_key_even_with_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("RUN_LIVE_GEMINI_TEST", "1")
    assert not _live_gemini_enabled()


def test_live_gemini_allows_explicit_opt_in_and_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("RUN_LIVE_GEMINI_TEST", "1")
    assert _live_gemini_enabled()


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    llm._client.cache_clear()
    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY is missing"):
        llm.ask_llm("hi")
    llm._client.cache_clear()


def test_invalid_json_gives_clear_error(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    monkeypatch.setattr(llm, "_generate", lambda prompt, **kw: "not json")
    with pytest.raises(llm.LLMError, match="expected JSON"):
        llm.ask_llm_json("x", Out)


def test_json_is_validated(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    monkeypatch.setattr(llm, "_generate", lambda prompt, **kw: '{"n": 3}')
    assert llm.ask_llm_json("x", Out).n == 3


# Live test: calls the real Gemini API only after explicit opt-in.
# Prompts must be synthetic only (free tier).
@pytest.mark.skipif(
    not _live_gemini_enabled(),
    reason="requires RUN_LIVE_GEMINI_TEST=1 and GEMINI_API_KEY",
)
def test_live_hello_gemini():
    try:
        answer = llm.ask_llm("Return exactly: HELLO_GEMINI")
    except llm.LLMError as error:
        if isinstance(error, llm.LLMRateLimitError):  # provider quota is not a code bug
            pytest.skip("Gemini free-tier rate limit reached")
        raise
    assert "HELLO_GEMINI" in answer
