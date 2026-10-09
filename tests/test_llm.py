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


@pytest.fixture(autouse=True)
def _no_backup_provider(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    with pytest.raises(llm.LLMError, match="No Gemini key found"):
        llm.ask_llm("hi")


def _fake_client_factory(calls, exhausted):
    class _Models:
        def __init__(self, key):
            self.key = key

        def generate_content(self, **kwargs):
            calls.append(self.key)
            if self.key in exhausted:
                raise llm.errors.APIError(429, {"error": {"message": "quota"}})
            return type("R", (), {"text": f"ok-{self.key}"})()

    class _Client:
        def __init__(self, key):
            self.models = _Models(key)

    return _Client


def test_rotates_to_next_key_when_one_is_rate_limited(monkeypatch):
    calls = []
    monkeypatch.setenv("GEMINI_API_KEYS", "a, b")
    monkeypatch.setenv("GEMINI_API_KEY", "c")
    monkeypatch.setattr(llm, "_client_for", _fake_client_factory(calls, {"a"}))
    monkeypatch.setattr(llm, "_active_key", 0)
    assert llm.ask_llm("hi") == "ok-b"
    assert llm.ask_llm("again") == "ok-b"
    assert calls == ["a", "b", "b"]  # the exhausted key is skipped afterwards


def test_all_keys_rate_limited_raises_rate_limit_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "a,b")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_client_for", _fake_client_factory([], {"a", "b"}))
    monkeypatch.setattr(llm, "_active_key", 0)
    with pytest.raises(llm.LLMRateLimitError):
        llm.ask_llm("hi")


def test_falls_back_to_lite_model_when_main_model_is_limited(monkeypatch):
    seen = []

    class _Models:
        def generate_content(self, model, **kwargs):
            seen.append(model)
            if model == "main-model":
                raise llm.errors.APIError(429, {"error": {"message": "quota"}})
            return type("R", (), {"text": f"ok-{model}"})()

    monkeypatch.setenv("GEMINI_API_KEY", "a")
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "main-model")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "lite-model")
    monkeypatch.setattr(llm, "_client_for", lambda key: type("C", (), {"models": _Models()})())
    monkeypatch.setattr(llm, "_active_key", 0)
    assert llm.ask_llm("hi") == "ok-lite-model"
    assert seen == ["main-model", "lite-model"]


def test_falls_back_to_xai_when_all_gemini_keys_are_limited(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "a,b")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.setattr(llm, "_client_for", _fake_client_factory([], {"a", "b"}))
    monkeypatch.setattr(llm, "_active_key", 0)
    monkeypatch.setattr(llm, "_generate_xai", lambda prompt, **kw: "from-xai")
    assert llm.ask_llm("hi") == "from-xai"


def test_xai_json_mode_parses_and_validates(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    seen = {}

    def fake_post(url, json, timeout, headers):
        seen["body"] = json
        payload = {"choices": [{"message": {"content": '{"n": 3}'}}]}
        return type("R", (), {"status_code": 200, "json": lambda self: payload})()

    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.ask_llm_json("x", Out).n == 3
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_xai_rate_limit_raises_rate_limit_error(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setattr(
        llm.httpx, "post", lambda *a, **k: type("R", (), {"status_code": 429})()
    )
    with pytest.raises(llm.LLMRateLimitError):
        llm.ask_llm("hi")


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
