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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    with pytest.raises(llm.LLMError, match="No AI provider key is configured in the backend"):
        llm.ask_llm("hi")


def test_missing_provider_error_explains_openrouter_setup_without_request(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)

    def unexpected(*args, **kwargs):
        pytest.fail("Missing credentials must not send an API request")

    monkeypatch.setattr(llm.httpx, "post", unexpected)
    with pytest.raises(llm.LLMError) as error:
        llm.ask_llm("hi")
    assert "OPENROUTER_API_KEY" in str(error.value)
    assert "Render" in str(error.value)
    assert "Frontend .env.local does not configure the backend" in str(error.value)


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


def test_openai_json_mode_parses_and_validates(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    def fake_post(url, json, timeout, headers):
        assert url == llm.OPENAI_URL
        assert headers == {"Authorization": "Bearer openai-test"}
        assert timeout == 12
        assert json["model"] == "custom-model"
        assert json["response_format"] == {"type": "json_object"}
        assert '"n"' in json["messages"][0]["content"]
        return llm.httpx.Response(
            200, json={"choices": [{"message": {"content": '{"n": 3}'}}]}
        )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", " openai-test ")
    monkeypatch.setenv("OPENAI_MODEL", "custom-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.ask_llm_json("x", Out).n == 3


def test_openai_after_gemini_rate_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a")
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setattr(llm, "_client_for", _fake_client_factory([], {"a"}))
    monkeypatch.setattr(llm, "_active_key", 0)
    monkeypatch.setattr(llm, "_generate_openai", lambda prompt, **kw: "from-openai")
    assert llm.ask_llm("hi") == "from-openai"


@pytest.mark.parametrize("xai_limited", [False, True])
def test_xai_precedes_openai(monkeypatch, xai_limited):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    calls = []

    def xai(prompt, **config):
        calls.append("xai")
        if xai_limited:
            raise llm.LLMRateLimitError("xai limited")
        return "from-xai"

    def openai(prompt, **config):
        calls.append("openai")
        return "from-openai"

    monkeypatch.setattr(llm, "_generate_xai", xai)
    monkeypatch.setattr(llm, "_generate_openai", openai)
    assert llm.ask_llm("hi") == ("from-openai" if xai_limited else "from-xai")
    assert calls == (["xai", "openai"] if xai_limited else ["xai"])


@pytest.mark.parametrize("provider", ["gemini", "xai"])
def test_openai_does_not_hide_non_quota_errors(monkeypatch, provider):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test")

    def fail(prompt, **config):
        raise llm.LLMError("invalid credentials")

    def unexpected(prompt, **config):
        pytest.fail("OpenAI must not be called for non-quota errors")

    if provider == "xai":
        monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setattr(llm, f"_generate_{provider}", fail)
    monkeypatch.setattr(llm, "_generate_openai", unexpected)
    with pytest.raises(llm.LLMError, match="invalid credentials"):
        llm.ask_llm("hi")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_openai_http_errors_are_explicit(monkeypatch, status):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: llm.httpx.Response(status))
    error_type = llm.LLMRateLimitError if status == 429 else llm.LLMError
    with pytest.raises(error_type, match="OpenAI"):
        llm._generate_openai("hi")


@pytest.mark.parametrize("error", [llm.httpx.ReadTimeout, llm.httpx.ConnectError])
def test_openai_network_errors_are_explicit(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error("network failed")

    monkeypatch.setattr(llm.httpx, "post", fail)
    with pytest.raises(llm.LLMError, match="OpenAI"):
        llm._generate_openai("hi")


@pytest.mark.parametrize("payload", [
    {}, {"choices": []},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": ["not text"]}}]},
    {"choices": [{"message": {"content": " "}}]},
])
def test_openai_invalid_responses_are_explicit(monkeypatch, payload):
    monkeypatch.setattr(
        llm.httpx, "post", lambda *a, **k: llm.httpx.Response(200, json=payload)
    )
    with pytest.raises(llm.LLMOutputError, match="OpenAI"):
        llm._generate_openai("hi")


def test_openai_text_uses_default_model(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    def fake_post(url, json, **kwargs):
        assert json["model"] == llm.DEFAULT_OPENAI_MODEL
        assert json["messages"] == [{"role": "user", "content": "hi"}]
        assert "response_format" not in json
        return llm.httpx.Response(
            200, json={"choices": [{"message": {"content": "hello"}}]}
        )

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm._generate_openai("hi") == "hello"


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


def test_claude_structured_result_and_request(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", " claude-test ")
    monkeypatch.setenv("ANTHROPIC_MODEL", "custom-claude")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")

    def post(url, json, timeout, headers):
        assert url == llm.ANTHROPIC_URL
        assert headers["x-api-key"] == "claude-test"
        assert headers["anthropic-version"] == "2023-06-01"
        assert timeout == 12
        assert json["model"] == "custom-claude"
        assert json["max_tokens"] == 8192
        assert json["messages"] == [{"role": "user", "content": "x"}]
        assert json["tools"][0]["input_schema"] == Out.model_json_schema()
        assert json["tool_choice"] == {"type": "tool", "name": "review_result"}
        return llm.httpx.Response(200, json={
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "review_result", "input": {"n": 3}}],
        })

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm.ask_llm_json("x", Out).n == 3


def test_claude_plain_text_default_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    def post(url, json, **kwargs):
        assert json["model"] == llm.DEFAULT_ANTHROPIC_MODEL
        assert "tools" not in json
        return llm.httpx.Response(200, json={
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}],
        })

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm._generate_anthropic("hi") == "hello\nworld"


@pytest.mark.parametrize("successful_provider", ["gemini", "xai", "openai", "anthropic"])
def test_claude_fallback_order(monkeypatch, successful_provider):
    for key in ["GEMINI_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        monkeypatch.setenv(key, "test-key")
    calls = []

    def generate(provider):
        def call(prompt, **config):
            calls.append(provider)
            if provider != successful_provider:
                raise llm.LLMRateLimitError("limited")
            return provider
        return call

    order = ["gemini", "xai", "openai", "anthropic"]
    for provider in order:
        monkeypatch.setattr(llm, f"_generate_{provider}", generate(provider))
    assert llm.ask_llm("hi") == successful_provider
    assert calls == order[:order.index(successful_provider) + 1]


@pytest.mark.parametrize("provider", ["gemini", "xai", "openai"])
def test_claude_does_not_hide_other_provider_errors(monkeypatch, provider):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-test")

    def fail(prompt, **config):
        raise llm.LLMError("invalid credentials")

    def unexpected(prompt, **config):
        pytest.fail("Claude must not be called for non-quota errors")

    monkeypatch.setattr(llm, f"_generate_{provider}", fail)
    monkeypatch.setattr(llm, "_generate_anthropic", unexpected)
    with pytest.raises(llm.LLMError, match="invalid credentials"):
        llm.ask_llm("hi")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 529])
def test_claude_http_errors(monkeypatch, status):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-test")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(status))
    error_type = llm.LLMRateLimitError if status == 429 else llm.LLMError
    with pytest.raises(error_type, match="Claude"):
        llm.ask_llm("hi")


@pytest.mark.parametrize("error", [llm.httpx.ReadTimeout, llm.httpx.ConnectError])
def test_claude_network_errors(monkeypatch, error):
    def fail(*a, **kw):
        raise error("network error")

    monkeypatch.setattr(llm.httpx, "post", fail)
    with pytest.raises(llm.LLMError, match="Claude"):
        llm._generate_anthropic("hi")


@pytest.mark.parametrize("payload", [
    {}, [], {"stop_reason": "end_turn", "content": []},
    {"stop_reason": "end_turn", "content": ["bad block"]},
    {"stop_reason": "end_turn", "content": [{"type": "text", "text": None}]},
    {"stop_reason": "end_turn", "content": [{"type": "text", "text": " "}]},
    {"stop_reason": "max_tokens", "content": [{"type": "text", "text": "partial"}]},
    {"stop_reason": "refusal", "content": [{"type": "text", "text": "refused"}]},
])
def test_claude_invalid_text_responses(monkeypatch, payload):
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(200, json=payload))
    with pytest.raises(llm.LLMOutputError, match="Claude"):
        llm._generate_anthropic("hi")


@pytest.mark.parametrize("blocks", [
    [], [{"type": "text", "text": '{"n": 3}'}],
    [{"type": "tool_use", "name": "wrong", "input": {"n": 3}}],
    [{"type": "tool_use", "name": "review_result", "input": None}],
    [{"type": "tool_use", "name": "review_result", "input": {"n": "not an int"}}],
    [{"type": "tool_use", "name": "review_result", "input": {"n": 3}}] * 2,
])
def test_claude_invalid_structured_responses(monkeypatch, blocks):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-test")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(
        200, json={"stop_reason": "tool_use", "content": blocks}
    ))
    with pytest.raises(llm.LLMOutputError):
        llm.ask_llm_json("x", Out)


def test_claude_non_json_response(monkeypatch):
    monkeypatch.setattr(
        llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(200, text="not JSON")
    )
    with pytest.raises(llm.LLMOutputError, match="Claude"):
        llm._generate_anthropic("hi")


@pytest.mark.parametrize("model", ["openrouter/free", "example/model:free"])
def test_openrouter_json_request_and_validation(monkeypatch, model):
    from pydantic import BaseModel

    class Out(BaseModel):
        n: int

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", " router-test ")
    monkeypatch.setenv("OPENROUTER_MODEL", model)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")

    def post(url, json, timeout, headers):
        assert url == llm.OPENROUTER_URL
        assert headers["Authorization"] == "Bearer router-test"
        assert timeout == 12
        assert json["model"] == model
        assert json["provider"] == {"require_parameters": True}
        assert json["response_format"] == {"type": "json_object"}
        assert '"n"' in json["messages"][0]["content"]
        assert "models" not in json
        return llm.httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"n": 3}'}}],
        })

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm.ask_llm_json("x", Out).n == 3


@pytest.mark.parametrize("model", ["openrouter/auto", "openai/gpt-4o", "model:free:paid"])
def test_openrouter_rejects_paid_models_before_request(monkeypatch, model):
    monkeypatch.setenv("OPENROUTER_MODEL", model)

    def unexpected(*a, **kw):
        pytest.fail("A paid model must not cause an HTTP request")

    monkeypatch.setattr(llm.httpx, "post", unexpected)
    with pytest.raises(llm.LLMError, match="Paid OpenRouter models are not enabled"):
        llm._generate_openrouter("hi")


def test_openrouter_free_default_plain_text(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    def post(url, json, **kwargs):
        assert json["model"] == "openrouter/free"
        assert json["messages"] == [{"role": "user", "content": "hi"}]
        assert "response_format" not in json
        return llm.httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
        })

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm._generate_openrouter("hi") == "hello"


@pytest.mark.parametrize("successful", ["gemini", "openrouter", "xai", "openai", "anthropic"])
def test_free_backup_precedes_paid_providers(monkeypatch, successful):
    order = ["gemini", "openrouter", "xai", "openai", "anthropic"]
    calls = []

    def generate(provider):
        def call(prompt, **config):
            calls.append(provider)
            if provider != successful:
                raise llm.LLMRateLimitError("limited")
            return provider
        return call

    for provider in order:
        monkeypatch.setenv(f"{provider.upper()}_API_KEY", "test-key")
        monkeypatch.setattr(llm, f"_generate_{provider}", generate(provider))
    assert llm.ask_llm("hi") == successful
    assert calls == order[:order.index(successful) + 1]


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 429, 500, 502])
def test_openrouter_errors_do_not_hide_failures(monkeypatch, status):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(status))
    error = llm.LLMRateLimitError if status == 429 else llm.LLMError
    with pytest.raises(error, match="OpenRouter"):
        llm.ask_llm("hi")


def test_openrouter_non_quota_error_does_not_call_paid_backup(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def unexpected(*a, **kw):
        pytest.fail("Paid fallback must not hide a non-quota error")

    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(401))
    monkeypatch.setattr(llm, "_generate_openai", unexpected)
    with pytest.raises(llm.LLMError, match="OpenRouter"):
        llm.ask_llm("hi")


@pytest.mark.parametrize("reason", ["length", "content_filter", "error", None])
def test_openrouter_incomplete_answers_are_rejected(monkeypatch, reason):
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(200, json={
        "choices": [{"finish_reason": reason, "message": {"content": "partial"}}],
    }))
    with pytest.raises(llm.LLMOutputError, match="OpenRouter"):
        llm._generate_openrouter("hi")


@pytest.mark.parametrize("payload", [
    {}, {"error": {"code": 502}}, {"choices": []},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
])
def test_openrouter_invalid_responses_are_rejected(monkeypatch, payload):
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **kw: llm.httpx.Response(200, json=payload))
    with pytest.raises(llm.LLMOutputError, match="OpenRouter"):
        llm._generate_openrouter("hi")


@pytest.mark.parametrize("error", [llm.httpx.ReadTimeout, llm.httpx.ConnectError])
def test_openrouter_network_errors(monkeypatch, error):
    def fail(*a, **kw):
        raise error("network failed")

    monkeypatch.setattr(llm.httpx, "post", fail)
    with pytest.raises(llm.LLMError, match="OpenRouter"):
        llm._generate_openrouter("hi")


def test_analysis_budget_limits_request_timeout_and_resets(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(llm, "monotonic", lambda: clock[0])
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "60")
    with llm.analysis_time_budget():
        assert llm._request_timeout() == 60
        clock[0] += 285
        assert llm._request_timeout() == 10
        clock[0] += 10
        with pytest.raises(llm.LLMTimeoutError, match="295-second"):
            llm._request_timeout()
        clock[0] = 390
    assert llm._analysis_deadline.get() is None
    assert llm._request_timeout() == 60


def test_expired_budget_does_not_call_another_provider(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(llm, "monotonic", lambda: clock[0])
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def limited(prompt, **config):
        clock[0] = 295
        raise llm.LLMRateLimitError("quota")

    def unexpected(prompt, **config):
        pytest.fail("Expired analysis must not call a backup")

    monkeypatch.setattr(llm, "_generate_gemini", limited)
    monkeypatch.setattr(llm, "_generate_openrouter", unexpected)
    with pytest.raises(llm.LLMTimeoutError):
        with llm.analysis_time_budget():
            llm.ask_llm("hi")
    assert llm._analysis_deadline.get() is None


def test_slow_answer_is_not_returned_as_completed_report(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(llm, "monotonic", lambda: clock[0])

    def slow(prompt, **config):
        clock[0] = 296
        return "late answer"

    monkeypatch.setattr(llm, "_generate", slow)
    with pytest.raises(llm.LLMTimeoutError):
        with llm.analysis_time_budget():
            llm.ask_llm("hi")


def test_gemini_request_has_remaining_timeout_and_no_sdk_retry(monkeypatch):
    calls = []

    class Models:
        def generate_content(self, **kwargs):
            options = kwargs["config"].http_options
            calls.append((options.timeout, options.retry_options.attempts))
            return type("R", (), {"text": "ok"})()

    clock = [0.0]
    monkeypatch.setattr(llm, "monotonic", lambda: clock[0])
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setattr(llm, "_client_for", lambda key: type("C", (), {"models": Models()})())
    with llm.analysis_time_budget():
        clock[0] = 290
        assert llm.ask_llm("hi") == "ok"
    assert calls == [(5000, 1)]


def test_analysis_can_complete_after_one_minute(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(llm, "monotonic", lambda: clock[0])

    def answer(prompt, **config):
        clock[0] = 240
        return "completed answer"

    monkeypatch.setattr(llm, "_generate", answer)
    with llm.analysis_time_budget():
        assert llm.ask_llm("hi") == "completed answer"
    assert llm._analysis_deadline.get() is None


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
