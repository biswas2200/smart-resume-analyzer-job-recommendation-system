"""The one analysis pipeline both routers run (POST /analyze with text,
POST /analyze-file with a file): detect the domain, score ATS, then parse,
match, find gaps and explain -- or lock the recommendations -- according to
the detected domain's engine (data/domains.json).

What happens, by the domain's engine:

  local  ->  local parse -> match -> gaps -> coaching narrative   (every domain, as shipped)
  llm    ->  LLM extraction -> match -> gaps -> coaching narrative   (opt-in, by flipping a
                                                                      domain's engine in domains.json)

The resume is read by our own NER model and dictionaries for every field; the LLM only writes the
coaching narrative, and a template stands in when it is unavailable.

Every account gets the same thing. Two deployment-level locks come before
that: LLM_PROVIDER=none (the Community Edition -- "community_edition") and
the operator's optional daily budget guard ("ai_budget_exhausted", off while
LLM_DAILY_BUDGET_USD is 0). A locked result still carries the ATS score,
detected domain and a profile card. ATS scoring and domain detection are
deterministic. `engine` is read from the domain entry, so moving a domain onto
the local pipeline later is a data change.
"""

import logging
import time

from app.models.schemas import AnalyzeResponse, DomainDetection, LockReason, ResumeProfile
from app.services import ats_score, gap_analysis, matcher
from app.services.dictionary_skills import GENERAL_TAXONOMY_PATH, find_skills
from app.services.domain_classifier import ENGINEERING_DOMAIN, detect_domain
from app.services.explainer import explain_results
from app.services.fingerprint import engine_fingerprint
from app.services.llm_client import ledger, llm_available, usage_summary
from app.services.normalizer import normalize_skills
from app.services.parser import parse_resume

LOCK_REASON_COMMUNITY_EDITION: LockReason = "community_edition"
LOCK_REASON_AI_BUDGET_EXHAUSTED: LockReason = "ai_budget_exhausted"

log = logging.getLogger(__name__)


def _parse_for_domain(resume_text: str, domain: DomainDetection) -> ResumeProfile:
    """Profile extraction for one domain: the local NER path for local-engine
    domains, the LLM extractor otherwise. Outside engineering the all-domain
    dictionary hits are merged in and everything is normalized against both
    taxonomies -- the same recall trick local_ner_parser.py uses with the
    engineering dictionary, and what makes the locked profile card useful.
    """
    if domain.engine == "llm":
        profile = parse_resume(resume_text, backend="llm", domain_name=domain.name)
    else:
        profile = parse_resume(resume_text, ner_skills=domain.domain == ENGINEERING_DOMAIN)

    if domain.domain != ENGINEERING_DOMAIN:
        profile.skills = normalize_skills(
            [*find_skills(resume_text, GENERAL_TAXONOMY_PATH), *profile.skills], include_general=True
        )
    return profile


def _lock_reason(domain: DomainDetection) -> LockReason | None:
    """Why this request cannot use the AI engine, or None if it can (or
    does not need to). The deployment first, then the operator's budget.
    """
    if domain.engine != "llm":
        return None
    if not llm_available():
        return LOCK_REASON_COMMUNITY_EDITION
    if ledger.over_daily_budget():
        return LOCK_REASON_AI_BUDGET_EXHAUSTED
    return None


def analyze_text(
    resume_text: str,
    top_n: int = 3,
    hidden_word_count: int = 0,
) -> AnalyzeResponse:
    """Run the pipeline and, when it made any LLM calls, attach what they
    cost (AnalyzeResponse.llm_usage) and whether a paid extraction ran
    (ai_extraction_used). `hidden_word_count` comes from the file
    extractor and only feeds the ATS "no_hidden_text" check."""
    start = time.perf_counter()
    with ledger.request_scope() as llm_calls:
        response = _analyze(resume_text, top_n, hidden_word_count)
    if llm_calls:
        response.llm_usage = usage_summary(llm_calls)
        response.ai_extraction_used = any(
            c.purpose == "extract" and not c.cache_hit for c in llm_calls
        )
    # Outcome only -- never the resume text or anything parsed out of it.
    log.info(
        "analysis domain=%s engine=%s confidence=%.2f ats=%.0f matches=%d locked=%s "
        "explanation=%s llm_calls=%d ai_extraction=%s chars=%d hidden_words=%d in %.0fms",
        response.domain.domain, response.domain.engine, response.domain.confidence,
        response.ats_score.score, len(response.matches), response.lock_reason or False,
        response.explanation_source, len(llm_calls), response.ai_extraction_used,
        len(resume_text), hidden_word_count, (time.perf_counter() - start) * 1000,
    )
    return response


def _analyze(resume_text: str, top_n: int, hidden_word_count: int = 0) -> AnalyzeResponse:
    domain = detect_domain(resume_text)
    ats = ats_score.score_resume(resume_text, hidden_word_count=hidden_word_count)
    lock_reason = _lock_reason(domain)

    if lock_reason is not None:
        # The profile card still comes from the local extractor (never the
        # LLM on a locked result); recommendations stay empty by design.
        profile = parse_resume(resume_text)
        profile.skills = normalize_skills(
            [*find_skills(resume_text, GENERAL_TAXONOMY_PATH), *profile.skills], include_general=True
        )
        explanation = explain_results(
            profile, ats, [], [], backend="template", domain=domain, locked=True, lock_reason=lock_reason
        )
        return AnalyzeResponse(
            profile=profile,
            domain=domain,
            ats_score=ats,
            matches=[],
            gaps=[],
            recommendations_locked=True,
            lock_reason=lock_reason,
            explanation=explanation.text,
            explanation_source=explanation.source,
            engine_fingerprint=engine_fingerprint(),
        )

    t = time.perf_counter()
    profile = _parse_for_domain(resume_text, domain)
    parsed_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    matches = matcher.match_roles(profile.skills, top_n=top_n, domain=domain.domain)
    gaps = gap_analysis.analyze_gaps(matches)
    log.debug(
        "parse %.0fms (skills=%d experience=%d education=%d), match+gaps %.0fms",
        parsed_ms, len(profile.skills), len(profile.experience), len(profile.education),
        (time.perf_counter() - t) * 1000,
    )
    explanation = explain_results(profile, ats, matches, gaps, backend="llm", domain=domain)
    return AnalyzeResponse(
        profile=profile,
        domain=domain,
        ats_score=ats,
        matches=matches,
        gaps=gaps,
        explanation=explanation.text,
        explanation_source=explanation.source,
        engine_fingerprint=engine_fingerprint(),
    )
