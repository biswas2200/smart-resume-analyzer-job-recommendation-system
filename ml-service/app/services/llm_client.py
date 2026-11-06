"""Thin, swappable interface over whichever LLM provider is configured.
parser.py and explainer.py depend on the LLMClient Protocol below rather
than any specific SDK directly, so tests can inject a mock and run with no
network access or credentials, and so adding a new provider never requires
touching the two files that actually use one.

Every real provider client shares one provider-agnostic layer
(_ProviderClient): a completion cache, so an unchanged resume analysed
twice is paid for once, and a usage ledger that reads
each response's token counts and prices them with the list prices in
Settings -- the only way to check what an analysis actually costs
against what was assumed. The SDK-specific half (_generate) is all a
provider has to implement.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, NamedTuple, Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Anything that can turn a (system prompt, user prompt) pair into a
    single text completion. The narrow shape lets parser.py/explainer.py
    stay provider-agnostic and lets tests supply a fake implementation.
    The keyword options are cost controls the callers know and the client
    applies however its SDK spells them: `purpose` labels the call in the
    usage ledger, `json_output` asks for a bare JSON object (no fences or
    prose to pay for and strip), `max_output_tokens` caps the answer.
    """

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        purpose: str = "completion",
        json_output: bool = False,
        max_output_tokens: int | None = None,
    ) -> str:
        """Return the model's text completion for the given prompts."""
        ...


class LLMUnavailableError(RuntimeError):
    """The configured provider cannot be used right now -- missing project
    id, no Application Default Credentials, unknown provider name. Raised
    lazily from get_llm_client() so the deterministic paths (which never
    build a client) are unaffected, and so callers on the LLM paths can
    degrade cleanly: explainer.py falls back to the template, the extraction
    path surfaces a clear error instead of a stack trace.
    """


# --------------------------------------------------------------------------
# Usage accounting
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMUsage:
    """What one completion cost: the provider's own token counts and the
    estimate they price out to. `thinking_tokens` is Gemini's reasoning
    output (billed as output); `cached_tokens` is the part of the prompt
    the provider served from its context cache (reported, but priced at
    the full input rate here -- a deliberate over-estimate).
    """

    provider: str
    model: str
    purpose: str
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    cached_tokens: int
    estimated_cost_usd: float
    cache_hit: bool
    at: float


class _RawUsage(NamedTuple):
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0


def estimate_cost_usd(prompt_tokens: int, output_tokens: int, thinking_tokens: int = 0) -> float:
    """Price a call with Settings.llm_input_usd_per_1m / llm_output_usd_per_1m.
    Thinking tokens are billed at the output rate (Gemini's rule)."""
    settings = get_settings()
    cost = (
        prompt_tokens * settings.llm_input_usd_per_1m
        + (output_tokens + thinking_tokens) * settings.llm_output_usd_per_1m
    ) / 1_000_000
    return round(cost, 8)


class UsageLedger:
    """Process-wide record of every LLM call: running totals since start,
    the most recent calls, and -- through request_scope() -- the calls made
    while one analysis ran, so services/pipeline.py can return that
    request's own usage in its response. Thread-safe: FastAPI runs the sync
    endpoints in a thread pool.
    """

    def __init__(self, keep_recent: int = 200) -> None:
        self._lock = threading.Lock()
        self._keep_recent = keep_recent
        self._recent: list[LLMUsage] = []
        self._scope: ContextVar[list[LLMUsage] | None] = ContextVar("llm_usage_scope", default=None)
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.started_at = time.time()
            self.calls = 0
            self.cache_hits = 0
            self.prompt_tokens = 0
            self.output_tokens = 0
            self.thinking_tokens = 0
            self.cached_tokens = 0
            self.estimated_cost_usd = 0.0
            self._recent.clear()
            # Spend in the current UTC day, for the daily budget guard.
            self._day = _utc_day()
            self.day_cost_usd = 0.0

    def record(self, usage: LLMUsage) -> None:
        with self._lock:
            self.calls += 1
            self.cache_hits += int(usage.cache_hit)
            self.prompt_tokens += usage.prompt_tokens
            self.output_tokens += usage.output_tokens
            self.thinking_tokens += usage.thinking_tokens
            self.cached_tokens += usage.cached_tokens
            self.estimated_cost_usd = round(self.estimated_cost_usd + usage.estimated_cost_usd, 8)
            self._roll_day_locked()
            self.day_cost_usd = round(self.day_cost_usd + usage.estimated_cost_usd, 8)
            self._recent.append(usage)
            del self._recent[: -self._keep_recent]
        scope = self._scope.get()
        if scope is not None:
            scope.append(usage)

    def over_daily_budget(self) -> bool:
        """True once today's estimated spend has reached
        Settings.llm_daily_budget_usd (0 = no budget). services/pipeline.py
        consults this before letting a request use the AI
        engine. Process-local: a soft brake, not a bill.
        """
        budget = get_settings().llm_daily_budget_usd
        if budget <= 0:
            return False
        with self._lock:
            self._roll_day_locked()
            return self.day_cost_usd >= budget

    def _roll_day_locked(self) -> None:
        today = _utc_day()
        if today != self._day:
            self._day = today
            self.day_cost_usd = 0.0

    @contextmanager
    def request_scope(self) -> Iterator[list[LLMUsage]]:
        """Collect the calls made inside the block (in addition to the
        process totals). Nested scopes each see only their own calls."""
        calls: list[LLMUsage] = []
        token = self._scope.set(calls)
        try:
            yield calls
        finally:
            self._scope.reset(token)

    def recent(self) -> list[LLMUsage]:
        with self._lock:
            return list(self._recent)


def _utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


ledger = UsageLedger()


def usage_summary(calls: list[LLMUsage]) -> "LLMUsageSummary":
    """Roll a list of ledger entries up into the API's LLMUsageSummary."""
    from app.models.schemas import LLMCallUsage, LLMUsageSummary

    return LLMUsageSummary(
        calls=len(calls),
        cache_hits=sum(c.cache_hit for c in calls),
        prompt_tokens=sum(c.prompt_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        thinking_tokens=sum(c.thinking_tokens for c in calls),
        cached_tokens=sum(c.cached_tokens for c in calls),
        estimated_cost_usd=round(sum(c.estimated_cost_usd for c in calls), 8),
        details=[
            LLMCallUsage(
                provider=c.provider, model=c.model, purpose=c.purpose,
                prompt_tokens=c.prompt_tokens, output_tokens=c.output_tokens,
                thinking_tokens=c.thinking_tokens, cached_tokens=c.cached_tokens,
                estimated_cost_usd=c.estimated_cost_usd, cache_hit=c.cache_hit,
            )
            for c in calls
        ],
    )


# --------------------------------------------------------------------------
# Provider clients
# --------------------------------------------------------------------------


def _cache_key(*parts: object) -> str:
    return hashlib.sha256("\x00".join(str(p) for p in parts).encode("utf-8")).hexdigest()


class _ProviderClient:
    """The provider-agnostic half of a real client: cache lookup, usage
    recording and logging around one SDK call. Subclasses set `provider`
    and `model` and implement _generate(); they never touch the ledger or
    the cache themselves.
    """

    provider: str = ""
    model: str = ""

    def __init__(self) -> None:
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = get_settings().llm_cache_size
        self._cache_lock = threading.Lock()

    def _generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_output: bool,
        max_output_tokens: int | None,
    ) -> tuple[str, _RawUsage]:
        raise NotImplementedError

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        purpose: str = "completion",
        json_output: bool = False,
        max_output_tokens: int | None = None,
    ) -> str:
        key = _cache_key(self.provider, self.model, purpose, json_output, max_output_tokens,
                         system_prompt, user_prompt)
        cached = self._cache_get(key)
        if cached is not None:
            ledger.record(LLMUsage(self.provider, self.model, purpose, 0, 0, 0, 0, 0.0, True, time.time()))
            log.info("llm cache hit provider=%s model=%s purpose=%s", self.provider, self.model, purpose)
            return cached

        text, raw = self._generate(
            system_prompt, user_prompt, json_output=json_output, max_output_tokens=max_output_tokens
        )
        usage = LLMUsage(
            self.provider, self.model, purpose,
            raw.prompt_tokens, raw.output_tokens, raw.thinking_tokens, raw.cached_tokens,
            estimate_cost_usd(raw.prompt_tokens, raw.output_tokens, raw.thinking_tokens),
            False, time.time(),
        )
        ledger.record(usage)
        log.info(
            "llm call provider=%s model=%s purpose=%s prompt_tokens=%d output_tokens=%d "
            "thinking_tokens=%d cached_tokens=%d est_cost_usd=%.6f",
            usage.provider, usage.model, usage.purpose, usage.prompt_tokens, usage.output_tokens,
            usage.thinking_tokens, usage.cached_tokens, usage.estimated_cost_usd,
        )
        self._cache_put(key, text)
        return text

    def _cache_get(self, key: str) -> str | None:
        if self._cache_size <= 0:
            return None
        with self._cache_lock:
            text = self._cache.get(key)
            if text is not None:
                self._cache.move_to_end(key)
            return text

    def _cache_put(self, key: str, text: str) -> None:
        if self._cache_size <= 0 or not text:
            return
        with self._cache_lock:
            self._cache[key] = text
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)


class GroqLLMClient(_ProviderClient):
    """LLMClient backed by the Groq API. Groq hosts several open-weight
    model families (Llama, Gemma, ...) behind one API, so which family is
    actually used is controlled entirely by Settings.groq_model -- this
    class never needs to change to swap models.
    """

    provider = "groq"

    def __init__(self) -> None:
        # Imported lazily so the `groq` package only needs to be installed
        # (and importable) when this provider is actually selected.
        from groq import Groq

        settings = get_settings()
        if not settings.groq_api_key:
            raise LLMUnavailableError(
                "LLM_PROVIDER=groq needs GROQ_API_KEY in the environment."
            )
        super().__init__()
        self._client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model

    def _generate(self, system_prompt, user_prompt, *, json_output, max_output_tokens):
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0 if json_output else 0.7,
        }
        if max_output_tokens:
            kwargs["max_tokens"] = max_output_tokens
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**kwargs)
        usage = getattr(response, "usage", None)
        raw = _RawUsage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        return response.choices[0].message.content or "", raw


class GeminiLLMClient(_ProviderClient):
    """LLMClient backed by Gemini on Vertex AI, via the google-genai SDK,
    authenticated with Application Default Credentials -- never an API key.
    Shares only the cache/ledger layer with GroqLLMClient; the two SDKs
    have unrelated request/response shapes, so _generate is written
    separately for each.
    """

    provider = "gemini"

    def __init__(self) -> None:
        # Imported lazily so google-genai only needs to be installed when
        # this provider is actually selected, matching the Groq client's
        # lazy-import pattern above.
        from google import genai
        from google.genai import types

        settings = get_settings()
        if not settings.google_cloud_project:
            raise LLMUnavailableError(
                "Gemini on Vertex AI needs GOOGLE_CLOUD_PROJECT set and "
                "Application Default Credentials available (run "
                "`gcloud auth application-default login`, or attach a "
                "service account on GCP)."
            )
        try:
            # vertexai=True routes to the Vertex AI endpoint and makes the
            # SDK resolve credentials through ADC; there is intentionally no
            # api_key argument anywhere in this service.
            self._client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
        except Exception as exc:  # DefaultCredentialsError and friends
            raise LLMUnavailableError(
                "Could not initialise Gemini on Vertex AI with Application "
                f"Default Credentials: {exc}"
            ) from exc
        super().__init__()
        self._types = types
        self.model = settings.gemini_model
        self._thinking_budget = settings.gemini_thinking_budget

    def _generate(self, system_prompt, user_prompt, *, json_output, max_output_tokens):
        types = self._types
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            # Extraction wants the same JSON for the same resume (and the
            # cache to be meaningful); the narrative can read a little
            # more naturally.
            temperature=0.0 if json_output else 0.7,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if json_output else None,
            thinking_config=(
                types.ThinkingConfig(thinking_budget=self._thinking_budget)
                if self._thinking_budget >= 0 else None
            ),
        )
        response = self._client.models.generate_content(
            model=self.model, contents=user_prompt, config=config
        )
        meta = getattr(response, "usage_metadata", None)
        raw = _RawUsage(
            prompt_tokens=getattr(meta, "prompt_token_count", 0) or 0,
            output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
            thinking_tokens=getattr(meta, "thoughts_token_count", 0) or 0,
            cached_tokens=getattr(meta, "cached_content_token_count", 0) or 0,
        )
        return response.text or "", raw


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the process-wide LLMClient singleton, building it from the
    configured provider (Settings.llm_provider) on first use. Cached so
    each provider's SDK client (and any connection it holds) is created
    once per process, not once per request. A failed build is not cached,
    so fixing the environment and retrying works without a restart.
    """
    global _default_client
    if _default_client is None:
        provider = get_settings().llm_provider
        if provider == "gemini":
            _default_client = GeminiLLMClient()
        elif provider == "groq":
            _default_client = GroqLLMClient()
        elif provider == "none":
            raise LLMUnavailableError(
                "The AI engine is disabled in this deployment (LLM_PROVIDER=none, "
                "Community Edition)."
            )
        else:
            raise LLMUnavailableError(
                f"Unknown LLM_PROVIDER '{provider}' -- expected 'gemini', 'groq' or 'none'."
            )
    return _default_client


def llm_available() -> bool:
    """Whether this deployment has an AI engine at all (LLM_PROVIDER is not
    "none"). Cheap and side-effect free -- it never builds a client -- so the
    pipeline can decide to lock rather than fail before spending anything.
    """
    return get_settings().llm_provider != "none"
