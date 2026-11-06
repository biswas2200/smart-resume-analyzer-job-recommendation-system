from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _capped_text(limit: int):
    """A str field cut to `limit` characters instead of rejected: a parsed
    profile comes from a parser or an LLM reading an uploaded file, and one
    runaway field should shorten, not fail the whole analysis. The limits
    sit under the backend's column sizes (V1__init_schema.sql: name 255,
    email 320, phone 50, skill 255), so a profile always saves."""
    return Annotated[str, AfterValidator(lambda value: value[:limit])]


def _capped_list(limit: int):
    """A list field cut to its first `limit` items, for the same reason."""
    return AfterValidator(lambda items: items[:limit])


ShortText = _capped_text(200)
Skill = _capped_text(80)


class ExperienceEntry(BaseModel):
    title: ShortText
    organization: ShortText = ""
    duration: ShortText = ""
    description: _capped_text(2000) = ""


class EducationEntry(BaseModel):
    degree: ShortText
    institution: ShortText = ""
    year: ShortText = ""


class ResumeProfile(BaseModel):
    # validate_assignment: the pipeline replaces `skills` after parsing
    # (normalisation, verification), and the caps must hold for that too.
    model_config = ConfigDict(validate_assignment=True)

    name: _capped_text(120) = ""
    email: _capped_text(254) = ""
    phone: _capped_text(40) = ""
    skills: Annotated[list[Skill], _capped_list(150)] = Field(default_factory=list)
    experience: Annotated[list[ExperienceEntry], _capped_list(30)] = Field(default_factory=list)
    education: Annotated[list[EducationEntry], _capped_list(30)] = Field(default_factory=list)


class ParseRequest(BaseModel):
    resume_text: str


class ParseResponse(BaseModel):
    profile: ResumeProfile


class DomainDetection(BaseModel):
    """Which job domain a resume belongs to, decided deterministically by
    domain_classifier.py (no LLM), plus how data/domains.json says it is
    served: `engine` is what decides whether an analysis needs the AI engine.
    """

    domain: str
    name: str
    confidence: float
    engine: Literal["local", "llm"]


class MatchRequest(BaseModel):
    skills: list[str]
    top_n: int = 5
    # Which catalogue to rank against (an id from data/domains.json).
    domain: str = "engineering"


class RoleMatch(BaseModel):
    role: str
    domain: str = "engineering"
    # One-line description from the catalogue, so the backend can fill in
    # Role.description without a second lookup.
    description: str = ""
    score: float
    matched_skills: list[str]
    missing_skills: list[str]


class EngineFingerprint(BaseModel):
    """Identifies exactly which core-engine artifact produced a response
    (FR-11.2): a Community user can compare this against the same field from
    a web deployment's GET /health to prove they're running the same engine
    (see docs/editions-and-parity.md).
    """

    engine_version: str
    ner_model_sha: str
    embed_model_sha: str
    taxonomy_sha: str
    weights_snapshot_id: str


class MatchResponse(BaseModel):
    matches: list[RoleMatch]
    engine_fingerprint: EngineFingerprint


class HealthResponse(BaseModel):
    status: str
    engine_fingerprint: EngineFingerprint


class AtsCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class AtsScoreRequest(BaseModel):
    resume_text: str
    target_keywords: list[str] = Field(default_factory=list)


class AtsScoreResponse(BaseModel):
    score: float
    max_score: float
    checks: list[AtsCheck]


class GapAnalysis(BaseModel):
    role: str
    missing_skills: list[str]


LockReason = Literal["community_edition", "ai_budget_exhausted"]


class JdMatchRequest(BaseModel):
    """One pasted job description against an already-extracted skill set
    (services/jd_match.py). `skills` are the candidate's, as the pipeline
    returned them; `domain` picks the catalogue for the closest-role hint."""

    skills: list[str]
    jd_text: str = Field(min_length=1, max_length=20_000)
    domain: str = "engineering"


class JdMatchResponse(BaseModel):
    # 0.6 * coverage + 0.4 * similarity, 2 dp -- see services/jd_match.py.
    score: float
    # Share of the JD's recognised skills the resume has exactly.
    coverage: float
    # Cosine similarity of the two skill sets' mean embeddings (partial credit).
    similarity: float
    jd_skills: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    # The catalogue role the JD most resembles, or None if no skill was recognised.
    closest_role: RoleMatch | None = None
    explanation: str
    engine_fingerprint: EngineFingerprint


class AnalyzeRequest(BaseModel):
    resume_text: str
    top_n: int = 3


class LLMCallUsage(BaseModel):
    """One LLM call's token counts and estimated cost (llm_client.LLMUsage).
    thinking_tokens are Gemini's reasoning tokens, billed as output;
    cache_hit calls cost nothing and report zero tokens."""

    provider: str
    model: str
    purpose: str
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int = 0
    cached_tokens: int = 0
    estimated_cost_usd: float
    cache_hit: bool = False


class LLMUsageSummary(BaseModel):
    """Totals over a set of LLM calls -- one analysis, or the whole process."""

    calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0
    estimated_cost_usd: float = 0.0
    details: list[LLMCallUsage] = Field(default_factory=list)


class LLMPricing(BaseModel):
    """The list prices the estimates were computed with (Settings)."""

    input_usd_per_1m: float
    output_usd_per_1m: float


class LLMUsageReport(BaseModel):
    """GET /llm-usage: process totals since start (or the last reset), the
    pricing assumption behind them, and the most recent calls."""

    since: str
    provider: str
    model: str
    pricing: LLMPricing
    totals: LLMUsageSummary


class AnalyzeResponse(BaseModel):
    profile: ResumeProfile
    domain: DomainDetection
    ats_score: AtsScoreResponse
    matches: list[RoleMatch]
    gaps: list[GapAnalysis]
    # True when the domain needs the AI engine and this request could not
    # use it: matches/gaps are then empty and lock_reason says why --
    # "community_edition" (no LLM provider in this deployment) or
    # "ai_budget_exhausted" (the operator's daily budget guard). See
    # services/pipeline.py.
    recommendations_locked: bool = False
    lock_reason: LockReason | None = None
    explanation: str
    explanation_source: Literal["template", "llm"]
    engine_fingerprint: EngineFingerprint
    # True only when a paid (non-cached) AI extraction ran for this request
    # -- what the operator's daily budget counts.
    ai_extraction_used: bool = False
    # What this analysis spent on LLM calls: None when it made none (every
    # local-engine result); a cache hit is listed as a call at zero cost.
    llm_usage: LLMUsageSummary | None = None


# --- Job recommendations (services/job_rank.py) -----------------------------


class JobText(BaseModel):
    """One job posting's text, for skill extraction. `id` is the backend's."""

    id: str
    title: str
    text: str = Field(default="", max_length=25_000)


class ExtractJobSkillsRequest(BaseModel):
    jobs: list[JobText] = Field(max_length=200)


class JobSkills(BaseModel):
    id: str
    skills: list[str]


class ExtractJobSkillsResponse(BaseModel):
    jobs: list[JobSkills]
    engine_fingerprint: EngineFingerprint


class RankJob(BaseModel):
    """A job to rank: its title and the skills extracted for it earlier."""

    id: str
    title: str
    skills: list[str] = []


class RankJobsRequest(BaseModel):
    """The candidate's skills (as the pipeline extracted them) and their top
    matched role titles, against the jobs to rank."""

    skills: list[str]
    roles: list[str] = []
    jobs: list[RankJob] = Field(max_length=5_000)
    top_n: int = Field(default=50, ge=1, le=500)


class RankedJob(BaseModel):
    id: str
    # 0.45 * coverage * evidence + 0.30 * similarity + 0.25 * role_fit, 2 dp
    # (evidence = min(1, job skills / 5)); a job whose skills couldn't be read
    # scores 0.5 * role_fit -- see services/job_rank.py.
    score: float
    coverage: float
    similarity: float
    role_fit: float
    matched_skills: list[str]
    missing_skills: list[str]
    # Which of the candidate's roles the job title is closest to, if any.
    closest_role: str | None = None
    explanation: str


class RankJobsResponse(BaseModel):
    jobs: list[RankedJob]
    engine_fingerprint: EngineFingerprint


# --- Job-market demand (services/market_demand.py) ---------------------------


class MarketDemandRequest(BaseModel):
    """Open jobs with their stored skills; the service groups them by role."""

    jobs: list[RankJob] = Field(max_length=20_000)


class SkillDemand(BaseModel):
    skill: str
    # Share of this role's open jobs that ask for the skill, 2 dp.
    share: float


class RoleDemand(BaseModel):
    role: str
    domain: str
    job_count: int
    # The skills these jobs ask for most, most-asked first.
    in_demand: list[SkillDemand]
    # One EMA signal in [0.5, 1.0] per skill in the role's catalogue entry
    # (FR-7.2's new_signal; see services/market_demand.py).
    signals: dict[str, float]


class MarketDemandResponse(BaseModel):
    roles: list[RoleDemand]
    # Jobs whose title matched no catalogue role closely enough.
    unassigned_jobs: int


class WeightsSnapshot(BaseModel):
    """The backend's weights export (FR-7.5). Accepts the backend's camelCase
    field names as well as the snake_case ones weights_snapshot.json uses."""

    model_config = ConfigDict(populate_by_name=True)

    snapshot_id: str = Field(alias="snapshotId")
    created_at: str = Field(default="", alias="createdAt")
    sha256: str = ""
    weights: dict[str, dict[str, float]]


class WeightsSnapshotAck(BaseModel):
    snapshot_id: str
    roles: int
