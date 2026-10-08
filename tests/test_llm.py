import os

import pytest

import llm


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


# Live test: calls the real Gemini API. Skipped when no key is set.
# Prompts must be synthetic only (free tier).
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set in .env")
def test_live_hello_gemini():
    try:
        answer = llm.ask_llm("Return exactly: HELLO_GEMINI")
    except llm.LLMError as error:
        if "rate limit" in str(error):  # free-tier quota is not a code bug
            pytest.skip("Gemini free-tier rate limit reached")
        raise
    assert "HELLO_GEMINI" in answer
