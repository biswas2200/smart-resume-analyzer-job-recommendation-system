from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
SERVICE_DIR = APP_DIR.parent
DATA_DIR = APP_DIR / "data"


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / a
    local .env file. Every field has a safe default so the service can
    start (and its tests can run) with no .env file present at all.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which LLM provider llm_client.get_llm_client() should build: "gemini"
    # (default -- Gemini on Vertex AI, authenticated with Google Application
    # Default Credentials, no API key), "groq" (optional, needs
    # GROQ_API_KEY), or "none" -- the Community Edition setting: no provider
    # is ever built, and domains served by the AI engine come back locked
    # with lock_reason "community_edition" instead of failing. Kept as a
    # plain string rather than an enum so a new provider only needs a new
    # branch in get_llm_client(), not a schema change here.
    llm_provider: str = "gemini"

    # Level for the app's own loggers (app.*): DEBUG, INFO, WARNING, ERROR.
    log_level: str = "INFO"
    # Also write logs to this file (rotated at 10 MB, 5 kept), e.g.
    # logs/ml-service.log. Empty: console only.
    log_file: str = ""

    # Which backend parser.parse_resume() should use: "local" (default --
    # runs a resume-NER model fully offline, no credentials or network
    # needed) or "llm" (routes through llm_provider; opt-in, since it costs
    # money and needs outbound network access).
    parser_backend: str = "local"
    # The local NER model: a Hugging Face model id, or a directory holding a
    # saved model (a relative path is resolved against ml-service/). Default:
    # run 1's teacher, yashpwr/resume-ner-bert fine-tuned on our resumes --
    # 84 % field F1 on DataTurks test and 90 % on unseen LiveCareer, against
    # 76 % / 64 % for the untouched yashpwr model (training/RESULTS.md).
    # Fetch it with scripts/fetch_ner_models.sh. The smaller distilled
    # student (65M parameters, 81 % / 90 %) sits next to it in
    # models/ner/student-run1; switch with NER_MODEL_NAME and
    # NER_MODEL_REVISION. To go back to the upstream model, set
    # NER_MODEL_NAME=yashpwr/resume-ner-bert and
    # NER_MODEL_REVISION=3ea6ecf44274c0947b6e627bd36c32ec0e8c3eb8.
    ner_model_name: str = "models/ner/teacher-run1"
    # The bucket folder holding that model, e.g.
    # gs://smart-resume-analyzer-a7x2-data/runs/teacher. When set and the
    # local folder is missing, the service downloads it at start-up with ADC
    # and checks it against NER_MODEL_REVISION before use
    # (local_ner_parser.ensure_local_model). Empty: the folder must already
    # exist (scripts/fetch_ner_models.sh).
    ner_model_gcs_uri: str = ""

    # Gemini runs on Vertex AI and authenticates with Application Default
    # Credentials (ADC): `gcloud auth application-default login` on a dev
    # machine, the attached service account on GCP. There is deliberately
    # no API-key field for Google -- credentials never live in config. The
    # env var names match what gcloud and the google-genai SDK already use,
    # so one `export GOOGLE_CLOUD_PROJECT=...` configures both.
    google_cloud_project: str = ""
    # "global" is Vertex AI's multi-region Gemini endpoint; a regional id
    # (e.g. "asia-south1") pins traffic to one region.
    google_cloud_location: str = "global"
    # gemini-2.5-flash-lite: measured on the sample resumes in
    # scripts/samples/ it extracts the same profile as gemini-2.5-flash
    # (22 skills, identical experience/education) at ~1/5 the price and
    # lower latency. Set gemini-2.5-flash for a slightly warmer narrative.
    gemini_model: str = "gemini-2.5-flash-lite"
    # Thinking budget sent with every Gemini call. 0 (default) switches
    # thinking off: both tasks here -- copying fields out of a resume into
    # JSON, and turning pre-computed scores into three short paragraphs --
    # are shallow, and thinking tokens are billed at the output rate (the
    # expensive side), typically 2-4x the visible answer. -1 sends no
    # thinking config and leaves the model's dynamic default in place (use
    # that for models that refuse a zero budget, e.g. gemini-2.5-pro).
    gemini_thinking_budget: int = 0

    # Groq -- optional alternative provider (LLM_PROVIDER=groq). Hosts
    # several open-weight model families (Llama, Gemma, ...) behind one API,
    # so switching between them is just changing groq_model -- it never
    # requires a code change in GroqLLMClient. The key is read from the
    # environment only.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    embedding_model: str = "all-MiniLM-L6-v2"

    # --- LLM cost controls (provider-agnostic; see ml-service/README.md) ---
    # Resume text is whitespace-compacted and cut to this many characters
    # before the extraction prompt (~4 chars per token, so ~4k tokens). A
    # two-page resume is 3-6k chars; this only trims pathological uploads.
    llm_max_input_chars: int = 16000
    # Output ceilings per task. Ceilings, not budgets -- you pay for what is
    # generated -- but they stop a runaway answer from costing 10x.
    llm_extract_max_output_tokens: int = 3072
    llm_narrate_max_output_tokens: int = 600
    # In-process cache of completions keyed by (provider, model, prompts):
    # re-analysing an unchanged resume costs nothing.
    # 0 disables it.
    llm_cache_size: int = 256
    # List prices the usage ledger (llm_client.UsageLedger) uses to turn
    # token counts into an estimated spend. Defaults are Vertex AI
    # gemini-2.5-flash-lite (gemini-2.5-flash is 0.30 / 2.50; thinking is
    # billed as output). Update them when the model changes -- they are
    # estimates, not billing.
    llm_input_usd_per_1m: float = 0.10
    llm_output_usd_per_1m: float = 0.40
    # Soft guard on what AI extraction may spend per UTC day, in the same
    # estimated dollars the ledger reports. Once the day's estimated spend
    # passes it, requests that would have used the AI engine come back
    # locked ("ai_budget_exhausted") instead. In-process only (resets with the process), so it is a
    # brake against a runaway, not billing enforcement. 0 disables it.
    llm_daily_budget_usd: float = 0.0

    # Which explainer.py backend explain_results() uses: "template" (default
    # -- deterministic, no network call, FR-5.4) or "llm" (opt-in
    # coaching narrative, routes through llm_provider). Mirrors
    # parser_backend's shape: a plain string, not a code change to add a
    # backend, and always overridable per-request via AnalyzeRequest.explainer.
    explainer_backend: str = "template"

    # Engine version stamped into every engine_fingerprint (FR-11.2, see
    # fingerprint.py) -- bumped on any release that changes scoring behavior,
    # so two deployments can prove they're running the same core engine.
    engine_version: str = "0.5.5"

    # Revision/commit pins for the two models fingerprint.py hashes into
    # engine_fingerprint.ner_model_sha / embed_model_sha. Real content-hash
    # pinning of the downloaded model weights themselves (rather than their
    # configured identifier) is a further step -- ONNX export and baking the
    # model into the release image, see docs/editions-and-parity.md -- that
    # this fingerprint mechanism doesn't depend on to exist.
    # The NER pin is a Hugging Face commit for a hub model, or the SHA-256 of
    # model.safetensors for a local directory; the loader refuses a local
    # model whose weights do not match it.
    ner_model_revision: str = "ab0fd6ea92dee31fed5e3f56a278197e8c55a358df19328a79981b00912fe189"
    # The embedding pin is the all-MiniLM-L6-v2 commit the role vectors and
    # domain scores were measured with.
    embedding_model_revision: str = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


@lru_cache
def get_settings() -> Settings:
    return Settings()
