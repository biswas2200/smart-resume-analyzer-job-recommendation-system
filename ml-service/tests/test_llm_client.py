"""Tests the provider-selection factory in llm_client.py -- verifies
get_llm_client() builds the right client class based on Settings.llm_provider
and that the Gemini client is constructed for Vertex AI with Application
Default Credentials (never an API key), without making any real network
calls to Groq or Google.
"""

import pytest

from app.config import Settings, get_settings
from app.services import llm_client


class _FakeGroqSdkClient:
    """Stand-in for groq.Groq -- just needs to accept the constructor call
    GroqLLMClient makes, never actually used to complete a request here.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


class _FakeGeminiSdkClient:
    """Stand-in for google.genai.Client. Records the keyword arguments it
    was built with so tests can assert the ADC/Vertex shape of the call;
    accepts api_key only so a regression that passes one is caught by an
    assertion rather than a TypeError.
    """

    last_kwargs: dict = {}

    def __init__(self, **kwargs) -> None:
        type(self).last_kwargs = kwargs


@pytest.fixture(autouse=True)
def _reset_llm_client_caches():
    """get_settings() and get_llm_client() both cache their result at
    module scope, so every test must clear both -- otherwise whichever
    test runs first "wins" and later tests silently reuse its client
    instead of exercising provider selection themselves.
    """
    get_settings.cache_clear()
    llm_client._default_client = None
    _FakeGeminiSdkClient.last_kwargs = {}
    yield
    get_settings.cache_clear()
    llm_client._default_client = None


def test_default_provider_is_gemini():
    # Checked on the field default (not by reading env) so a developer's
    # local .env can't make this pass or fail.
    assert Settings.model_fields["llm_provider"].default == "gemini"


def test_settings_have_no_google_api_key_field():
    # Google access is ADC-only by design: there must be no key field to
    # fill in, so no key can ever end up in config or a .env file.
    assert not any("gemini_api_key" in name or "google_api_key" in name
                   for name in Settings.model_fields)


def test_gemini_client_is_built_for_vertex_ai_with_adc(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
    monkeypatch.setattr("google.genai.Client", _FakeGeminiSdkClient)

    client = llm_client.get_llm_client()

    assert isinstance(client, llm_client.GeminiLLMClient)
    kwargs = _FakeGeminiSdkClient.last_kwargs
    assert kwargs.get("vertexai") is True
    assert kwargs.get("project") == "test-project"
    assert kwargs.get("location") == "asia-south1"
    assert "api_key" not in kwargs


def test_gemini_client_requires_google_cloud_project(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
    monkeypatch.setattr("google.genai.Client", _FakeGeminiSdkClient)

    with pytest.raises(llm_client.LLMUnavailableError, match="GOOGLE_CLOUD_PROJECT"):
        llm_client.get_llm_client()

    # A failed build must not be cached, so fixing the env and retrying
    # works without a process restart.
    assert llm_client._default_client is None


def test_gemini_credential_failure_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    class _NoCredentials:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError("Your default credentials were not found")

    monkeypatch.setattr("google.genai.Client", _NoCredentials)

    with pytest.raises(llm_client.LLMUnavailableError, match="Default Credentials"):
        llm_client.get_llm_client()


def test_get_llm_client_selects_groq_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("groq.Groq", _FakeGroqSdkClient)

    client = llm_client.get_llm_client()

    assert isinstance(client, llm_client.GroqLLMClient)


def test_groq_requires_its_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setattr("groq.Groq", _FakeGroqSdkClient)

    with pytest.raises(llm_client.LLMUnavailableError, match="GROQ_API_KEY"):
        llm_client.get_llm_client()


def test_provider_none_is_the_community_edition_and_builds_nothing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")

    assert llm_client.llm_available() is False
    with pytest.raises(llm_client.LLMUnavailableError, match="Community Edition"):
        llm_client.get_llm_client()
    assert llm_client._default_client is None


def test_llm_available_for_a_real_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")

    assert llm_client.llm_available() is True


def test_daily_budget_guard_trips_on_estimated_spend(monkeypatch):
    import time

    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "0.001")
    get_settings.cache_clear()
    llm_client.ledger.reset()
    spend = lambda usd: llm_client.ledger.record(llm_client.LLMUsage(
        "gemini", "m", "extract", 1, 1, 0, 0, usd, False, time.time()))

    assert llm_client.ledger.over_daily_budget() is False
    spend(0.0006)
    assert llm_client.ledger.over_daily_budget() is False
    spend(0.0006)
    assert llm_client.ledger.over_daily_budget() is True

    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "0")
    get_settings.cache_clear()
    assert llm_client.ledger.over_daily_budget() is False  # 0 = no budget


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with pytest.raises(llm_client.LLMUnavailableError, match="Unknown LLM_PROVIDER"):
        llm_client.get_llm_client()


def test_get_llm_client_caches_the_same_instance_across_calls(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setattr("google.genai.Client", _FakeGeminiSdkClient)

    first = llm_client.get_llm_client()
    second = llm_client.get_llm_client()

    assert first is second


# ---------------------------------------------------------------------------
# Cost controls: generation config, usage ledger, completion cache
# ---------------------------------------------------------------------------


class _FakeUsageMetadata:
    def __init__(self, prompt=1000, candidates=400, thoughts=0, cached=0) -> None:
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.thoughts_token_count = thoughts
        self.cached_content_token_count = cached


class _FakeGeminiResponse:
    def __init__(self, text: str, usage: _FakeUsageMetadata) -> None:
        self.text = text
        self.usage_metadata = usage


class _RecordingGeminiSdkClient:
    """Fake google.genai.Client whose models.generate_content records the
    call and returns a canned response with usage metadata -- so the exact
    generation config the client sends can be asserted without network."""

    calls: list[dict] = []
    response = _FakeGeminiResponse('{"name": "Jane"}', _FakeUsageMetadata())

    def __init__(self, **kwargs) -> None:
        outer = self

        class _Models:
            def generate_content(self, **kwargs):
                type(outer).calls.append(kwargs)
                return type(outer).response

        self.models = _Models()


@pytest.fixture
def gemini_client(monkeypatch):
    # Pinned explicitly so a developer's local .env (a different model or
    # price) cannot change what these tests assert.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_THINKING_BUDGET", "0")
    monkeypatch.setenv("LLM_CACHE_SIZE", "256")
    monkeypatch.setenv("LLM_INPUT_USD_PER_1M", "0.30")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_1M", "2.50")
    monkeypatch.setattr("google.genai.Client", _RecordingGeminiSdkClient)
    _RecordingGeminiSdkClient.calls = []
    _RecordingGeminiSdkClient.response = _FakeGeminiResponse('{"name": "Jane"}', _FakeUsageMetadata())
    llm_client.ledger.reset()
    return llm_client.get_llm_client()


def test_gemini_extraction_call_disables_thinking_and_asks_for_json(gemini_client):
    gemini_client.complete("sys", "resume text", purpose="extract", json_output=True, max_output_tokens=3072)

    (call,) = _RecordingGeminiSdkClient.calls
    config = call["config"]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "resume text"
    assert config.system_instruction == "sys"
    assert config.thinking_config.thinking_budget == 0
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 3072
    assert config.temperature == 0.0


def test_gemini_narrative_call_is_plain_text_with_its_own_cap(gemini_client):
    gemini_client.complete("sys", "scores", purpose="narrate", max_output_tokens=600)

    config = _RecordingGeminiSdkClient.calls[0]["config"]
    assert config.response_mime_type is None
    assert config.max_output_tokens == 600
    assert config.thinking_config.thinking_budget == 0


def test_negative_thinking_budget_sends_no_thinking_config(monkeypatch, gemini_client):
    monkeypatch.setenv("GEMINI_THINKING_BUDGET", "-1")
    get_settings.cache_clear()
    llm_client._default_client = None
    client = llm_client.get_llm_client()

    client.complete("sys", "x")

    assert _RecordingGeminiSdkClient.calls[-1]["config"].thinking_config is None


def test_usage_is_read_from_the_response_and_priced(gemini_client):
    _RecordingGeminiSdkClient.response = _FakeGeminiResponse(
        "ok", _FakeUsageMetadata(prompt=1000, candidates=400, thoughts=100)
    )

    with llm_client.ledger.request_scope() as calls:
        gemini_client.complete("sys", "x", purpose="extract")

    (usage,) = calls
    assert (usage.prompt_tokens, usage.output_tokens, usage.thinking_tokens) == (1000, 400, 100)
    # 1000 * 0.30/1M + (400 + 100) * 2.50/1M -- thinking is billed as output.
    assert usage.estimated_cost_usd == pytest.approx(0.0003 + 0.00125)
    assert usage.purpose == "extract" and usage.cache_hit is False
    assert llm_client.ledger.calls == 1
    assert llm_client.ledger.estimated_cost_usd == pytest.approx(usage.estimated_cost_usd)


def test_identical_prompts_hit_the_cache_and_cost_nothing(gemini_client):
    first = gemini_client.complete("sys", "same resume", purpose="extract", json_output=True)
    second = gemini_client.complete("sys", "same resume", purpose="extract", json_output=True)

    assert first == second == '{"name": "Jane"}'
    assert len(_RecordingGeminiSdkClient.calls) == 1
    assert llm_client.ledger.calls == 2 and llm_client.ledger.cache_hits == 1
    hit = llm_client.ledger.recent()[-1]
    assert hit.cache_hit is True and hit.estimated_cost_usd == 0.0


def test_cache_key_includes_the_options(gemini_client):
    gemini_client.complete("sys", "text", purpose="extract", json_output=True)
    gemini_client.complete("sys", "text", purpose="narrate", json_output=False)

    assert len(_RecordingGeminiSdkClient.calls) == 2


def test_cache_can_be_disabled(monkeypatch, gemini_client):
    monkeypatch.setenv("LLM_CACHE_SIZE", "0")
    get_settings.cache_clear()
    llm_client._default_client = None
    client = llm_client.get_llm_client()

    client.complete("sys", "text")
    client.complete("sys", "text")

    assert len(_RecordingGeminiSdkClient.calls) == 2


def test_request_scope_collects_only_its_own_calls(gemini_client):
    gemini_client.complete("sys", "outside")
    with llm_client.ledger.request_scope() as calls:
        gemini_client.complete("sys", "inside")

    assert [c for c in calls] and len(calls) == 1
    assert llm_client.ledger.calls == 2


def test_groq_call_sets_json_mode_and_caps(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    recorded: list[dict] = []

    class _Usage:
        prompt_tokens = 50
        completion_tokens = 20

    class _Choice:
        class message:
            content = '{"a": 1}'

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    class _FakeGroq:
        def __init__(self, api_key: str) -> None:
            outer = self

            class _Completions:
                def create(self, **kwargs):
                    recorded.append(kwargs)
                    return _Resp()

            class _Chat:
                completions = _Completions()

            self.chat = _Chat()

    monkeypatch.setattr("groq.Groq", _FakeGroq)
    llm_client.ledger.reset()

    text = llm_client.get_llm_client().complete("s", "u", purpose="extract", json_output=True, max_output_tokens=99)

    assert text == '{"a": 1}'
    (call,) = recorded
    assert call["response_format"] == {"type": "json_object"}
    assert call["max_tokens"] == 99 and call["temperature"] == 0.0
    usage = llm_client.ledger.recent()[-1]
    assert (usage.prompt_tokens, usage.output_tokens, usage.provider) == (50, 20, "groq")
