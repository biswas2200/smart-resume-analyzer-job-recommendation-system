"""services/pipeline.py -- the domain-engine cases and the deployment-level
locks. Every model and the LLM are faked: the point here is the routing
(which parser runs, whether the LLM is ever touched, whether and why
recommendations lock, whether a paid extraction is reported), not the
models' output.
"""

import pytest

from app.models.schemas import (
    AtsCheck,
    AtsScoreResponse,
    DomainDetection,
    GapAnalysis,
    ResumeProfile,
    RoleMatch,
)
from app.services import pipeline
from app.services.explainer import Explanation

ENGINEERING = DomainDetection(domain="engineering", name="Engineering & Technology",
                              confidence=0.8, engine="local")
HEALTHCARE = DomainDetection(domain="healthcare", name="Healthcare & Life Sciences",
                             confidence=0.8, engine="llm")
ATS = AtsScoreResponse(score=60, max_score=80, checks=[AtsCheck(name="contact_email", passed=True, detail="ok")])


class Calls:
    """Records which seams the pipeline exercised."""

    def __init__(self) -> None:
        self.parse: list[dict] = []
        self.match: list[dict] = []
        self.explain: list[dict] = []
        self.ner_skills: list[bool] = []


@pytest.fixture
def calls(monkeypatch) -> Calls:
    recorded = Calls()

    def fake_parse(resume_text, client=None, backend=None, domain_name=None, ner_skills=True):
        recorded.parse.append({"backend": backend, "domain_name": domain_name})
        recorded.ner_skills.append(ner_skills)
        skills = ["Python", "SQL"] if backend != "llm" else ["Nursing", "Patient Care"]
        return ResumeProfile(name="Sam", skills=skills)

    def fake_match(skills, top_n=5, domain="engineering"):
        recorded.match.append({"skills": skills, "top_n": top_n, "domain": domain})
        return [RoleMatch(role=f"{domain} role", domain=domain, score=0.7,
                          matched_skills=skills[:1], missing_skills=["Other"])]

    def fake_explain(profile, ats, matches, gaps, client=None, backend=None, domain=None, locked=False,
                     lock_reason=None):
        recorded.explain.append({"backend": backend, "locked": locked, "n_matches": len(matches)})
        return Explanation(text=f"{backend}:{'locked' if locked else 'open'}",
                           source="llm" if backend == "llm" and not locked else "template")

    monkeypatch.setattr(pipeline, "parse_resume", fake_parse)
    monkeypatch.setattr(pipeline.matcher, "match_roles", fake_match)
    monkeypatch.setattr(pipeline, "explain_results", fake_explain)
    monkeypatch.setattr(pipeline.ats_score, "score_resume", lambda text, hidden_word_count=0: ATS)
    monkeypatch.setattr(pipeline, "find_skills", lambda text, path=None: [])
    monkeypatch.setattr(pipeline.gap_analysis, "analyze_gaps",
                        lambda matches: [GapAnalysis(role=m.role, missing_skills=m.missing_skills) for m in matches])
    return recorded


def _forbid_llm(monkeypatch):
    from app.services import llm_client

    def boom():
        raise AssertionError("a local-engine analysis must never build an LLM client")

    monkeypatch.setattr(llm_client, "get_llm_client", boom)


def _forbid_llm(monkeypatch):
    from app.services import llm_client

    def boom():
        raise AssertionError("this analysis must never build an LLM client")

    monkeypatch.setattr(llm_client, "get_llm_client", boom)


def _record(purpose: str, cache_hit: bool = False) -> None:
    import time
    from app.services import llm_client

    llm_client.ledger.record(llm_client.LLMUsage(
        "gemini", "gemini-2.5-flash-lite", purpose, 0 if cache_hit else 850, 0 if cache_hit else 480,
        0, 0, 0.0 if cache_hit else 0.00028, cache_hit, time.time()))


def test_engineering_keeps_the_local_parse_and_narrates_with_the_llm(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)

    result = pipeline.analyze_text("resume", top_n=3)

    assert result.domain == ENGINEERING
    assert result.recommendations_locked is False and result.lock_reason is None
    assert calls.parse == [{"backend": None, "domain_name": None}]
    assert calls.match[0]["domain"] == "engineering" and calls.match[0]["top_n"] == 3
    assert calls.explain == [{"backend": "llm", "locked": False, "n_matches": 1}]
    assert result.matches[0].role == "engineering role"
    assert result.explanation_source == "llm"


def test_non_engineering_extracts_with_llm_and_matches_in_that_domain(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: HEALTHCARE)

    result = pipeline.analyze_text("resume", top_n=2)

    assert result.recommendations_locked is False
    assert calls.parse == [{"backend": "llm", "domain_name": "Healthcare & Life Sciences"}]
    assert calls.match == [{"skills": ["Nursing", "Patient Care"], "top_n": 2, "domain": "healthcare"}]
    assert result.matches[0].domain == "healthcare"
    assert calls.explain[0]["backend"] == "llm"
    assert result.explanation_source == "llm"


def test_general_dictionary_hits_are_merged_into_non_engineering_profiles(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: HEALTHCARE)
    monkeypatch.setattr(pipeline, "find_skills", lambda text, path=None: ["ACLS", "BLS"])

    result = pipeline.analyze_text("resume")

    assert result.profile.skills[:2] == ["ACLS", "BLS"]
    assert "Nursing" in result.profile.skills


def test_a_local_engine_domain_is_never_locked(monkeypatch, calls):
    # Locking is about needing the AI engine: a domain that runs on the local
    # pipeline never needs it, whatever its field.
    local_legal = DomainDetection(domain="legal", name="Legal & Compliance", confidence=0.7, engine="local")
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: local_legal)

    result = pipeline.analyze_text("resume")

    assert result.recommendations_locked is False
    assert calls.parse[-1] == {"backend": None, "domain_name": None}  # local engine, no LLM extraction
    assert calls.match[-1]["domain"] == "legal"


def test_an_ai_domain_extracts_once_and_reports_the_paid_extraction(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: HEALTHCARE)
    plain_parse = pipeline.parse_resume

    def parse_and_record(*args, **kwargs):
        if kwargs.get("backend") == "llm":
            _record("extract")
        return plain_parse(*args, **kwargs)

    monkeypatch.setattr(pipeline, "parse_resume", parse_and_record)

    result = pipeline.analyze_text("resume")

    assert result.recommendations_locked is False and result.lock_reason is None
    assert calls.parse == [{"backend": "llm", "domain_name": "Healthcare & Life Sciences"}]
    assert result.ai_extraction_used is True
    assert result.llm_usage is not None and result.llm_usage.calls == 1


def test_engineering_spends_no_extraction(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)

    result = pipeline.analyze_text("resume")

    assert result.recommendations_locked is False
    assert calls.parse == [{"backend": None, "domain_name": None}]
    assert result.ai_extraction_used is False


def test_a_cached_extraction_does_not_count_as_a_paid_extraction(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: HEALTHCARE)
    plain_parse = pipeline.parse_resume

    def parse_from_cache(*args, **kwargs):
        _record("extract", cache_hit=True)
        return plain_parse(*args, **kwargs)

    monkeypatch.setattr(pipeline, "parse_resume", parse_from_cache)

    result = pipeline.analyze_text("resume")

    assert result.recommendations_locked is False
    assert result.ai_extraction_used is False
    assert result.llm_usage is not None and result.llm_usage.cache_hits == 1


def test_a_narrative_alone_is_not_a_paid_extraction(monkeypatch, calls):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)
    plain_explain = pipeline.explain_results

    def explain_and_record(*args, **kwargs):
        _record("narrate")
        return plain_explain(*args, **kwargs)

    monkeypatch.setattr(pipeline, "explain_results", explain_and_record)

    result = pipeline.analyze_text("resume")

    assert result.ai_extraction_used is False  # narrate is not an extraction
    assert result.llm_usage is not None and result.llm_usage.details[0].purpose == "narrate"


def test_community_edition_locks_ai_domains_with_its_own_reason(monkeypatch, calls):
    from app.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: HEALTHCARE)
    _forbid_llm(monkeypatch)
    try:
        result = pipeline.analyze_text("resume")
    finally:
        get_settings.cache_clear()

    assert result.recommendations_locked is True
    assert result.lock_reason == pipeline.LOCK_REASON_COMMUNITY_EDITION
    assert result.matches == [] and result.ats_score == ATS
    assert all(c["backend"] is None for c in calls.parse)  # local profile card only
    assert calls.explain == [{"backend": "template", "locked": True, "n_matches": 0}]


def test_community_edition_still_serves_engineering_in_full(monkeypatch, calls):
    from app.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)
    try:
        result = pipeline.analyze_text("resume")
    finally:
        get_settings.cache_clear()

    assert result.recommendations_locked is False
    assert result.matches[0].role == "engineering role"


def test_daily_budget_guard_locks_ai_domains_for_everyone(monkeypatch, calls):
    from app.services import llm_client

    monkeypatch.setattr(llm_client.ledger, "over_daily_budget", lambda: True)
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: HEALTHCARE)
    _forbid_llm(monkeypatch)

    result = pipeline.analyze_text("resume")

    assert result.recommendations_locked is True
    assert result.lock_reason == pipeline.LOCK_REASON_AI_BUDGET_EXHAUSTED
    assert result.matches == []


def test_the_budget_guard_never_touches_a_local_engine_domain(monkeypatch, calls):
    from app.services import llm_client

    monkeypatch.setattr(llm_client.ledger, "over_daily_budget", lambda: True)
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)

    assert pipeline.analyze_text("resume").recommendations_locked is False


def test_llm_usage_is_attached_only_when_the_analysis_called_an_llm(monkeypatch, calls):
    import time
    from app.services import llm_client

    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)

    plain = pipeline.analyze_text("text")
    assert plain.llm_usage is None

    plain_explain = pipeline.explain_results

    def explain_and_record_usage(*args, **kwargs):
        llm_client.ledger.record(llm_client.LLMUsage(
            "gemini", "gemini-2.5-flash", "narrate", 450, 300, 0, 0, 0.000885, False, time.time()))
        return plain_explain(*args, **kwargs)

    monkeypatch.setattr(pipeline, "explain_results", explain_and_record_usage)

    narrated = pipeline.analyze_text("text")
    assert narrated.llm_usage is not None
    assert narrated.llm_usage.calls == 1
    assert narrated.llm_usage.details[0].purpose == "narrate"
    assert narrated.llm_usage.estimated_cost_usd == pytest.approx(0.000885)


def test_analysis_logs_its_outcome_but_not_the_resume(monkeypatch, calls, caplog):
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)

    with caplog.at_level("INFO", logger="app.services.pipeline"):
        pipeline.analyze_text("Jane Doe jane@example.com")

    line = caplog.records[-1].getMessage()
    assert "domain=engineering" in line and "engine=local" in line and "matches=1" in line
    assert "Jane" not in line and "jane@example.com" not in line


def test_a_local_engine_domain_outside_engineering_is_read_locally_without_the_ner_skill_spans(monkeypatch, calls):
    # Every field is read by our own parser. The NER model was trained on IT resumes, so outside
    # engineering its "Skills" spans are not trusted; engineering keeps them.
    local_hr = DomainDetection(domain="human_resources", name="Human Resources", confidence=0.7, engine="local")
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: local_hr)
    pipeline.analyze_text("resume")
    monkeypatch.setattr(pipeline, "detect_domain", lambda text: ENGINEERING)
    pipeline.analyze_text("resume")

    assert calls.parse == [{"backend": None, "domain_name": None}] * 2
    assert calls.ner_skills == [False, True]
