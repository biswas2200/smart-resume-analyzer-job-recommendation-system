"""Text-in analysis endpoints: the caller already has resume text (not a raw
file), so each endpoint here skips straight to its pipeline stage. Kept as
its own router, separate from upload.py, since file handling (upload.py) and
text-in analysis (this file) are distinct concerns -- upload.py's endpoints
just extract text and then delegate to the exact same pipeline functions
used below.
"""

from fastapi import APIRouter

from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AtsScoreRequest,
    AtsScoreResponse,
    DomainDetection,
    JdMatchRequest,
    JdMatchResponse,
    MatchRequest,
    MatchResponse,
    ParseRequest,
    ParseResponse,
)
from app.services import ats_score, jd_match, matcher, pipeline
from app.services.domain_classifier import detect_domain
from app.services.fingerprint import engine_fingerprint
from app.services.parser import parse_resume

router = APIRouter()


@router.post("/parse")
def parse(request: ParseRequest) -> ParseResponse:
    """Extract a structured profile from raw resume text via the configured
    parsing backend (local NER by default, LLM if PARSER_BACKEND=llm)."""
    profile = parse_resume(request.resume_text)
    return ParseResponse(profile=profile)


@router.post("/detect-domain")
def detect(request: ParseRequest) -> DomainDetection:
    """Which job domain the resume belongs to, and the engine that
    serves it -- deterministic, no LLM (see domain_classifier.py)."""
    return detect_domain(request.resume_text)


@router.post("/match")
def match(request: MatchRequest) -> MatchResponse:
    """Rank one domain's roles against an already-known skill list by
    embedding cosine similarity (see matcher.py) -- for a caller that has
    skills but not raw resume text, e.g. a profile-edit flow."""
    matches = matcher.match_roles(request.skills, top_n=request.top_n, domain=request.domain)
    return MatchResponse(matches=matches, engine_fingerprint=engine_fingerprint())


@router.post("/match-jd")
def match_jd(request: JdMatchRequest) -> JdMatchResponse:
    """How well an already-extracted skill set covers one pasted job
    description: score, matched/missing JD skills and the closest catalogue
    role (see jd_match.py). Deterministic, no LLM -- the backend exposes it
    as POST /resumes/{id}/jd-match."""
    return jd_match.match_jd(request.skills, request.jd_text, domain=request.domain)


@router.post("/ats-score")
def score(request: AtsScoreRequest) -> AtsScoreResponse:
    """Deterministic ATS compatibility score for raw resume text (see
    ats_score.py) -- no parsing or matching, just the rule-based checks."""
    return ats_score.score_resume(request.resume_text, request.target_keywords)


@router.post("/analyze")
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Full pipeline in one call: detect domain, ATS-score, parse, match
    roles, find skill gaps, and explain -- or lock recommendations when the
    domain needs the AI engine and this request may not use it (see
    services/pipeline.py). The text-in counterpart to upload.py's
    analyze_file()."""
    return pipeline.analyze_text(
        request.resume_text, top_n=request.top_n
    )
