"""Tests explainer.py's backend selection and template rendering. The LLM
path (via a mocked client) is covered by test_pipeline.py; this file covers
what's new here: the deterministic TemplateExplainer that's now the default
(FR-5.4), and the NFR-3.1 fallback to it when the LLM backend fails.
"""

import pytest

from app.config import get_settings
from app.models.schemas import AtsCheck, AtsScoreResponse, GapAnalysis, ResumeProfile, RoleMatch
from app.services.explainer import explain_results, render_template


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _RaisingLLMClient:
    def complete(self, system_prompt: str, user_prompt: str, **options) -> str:
        raise RuntimeError("simulated LLM outage")


def _profile_ats_matches_gaps():
    profile = ResumeProfile(name="Jane Doe", skills=["Python"])
    ats = AtsScoreResponse(
        score=70,
        max_score=100,
        checks=[
            AtsCheck(name="contact_email", passed=True, detail="Email found."),
            AtsCheck(name="contact_phone", passed=False, detail="No phone number found."),
        ],
    )
    matches = [RoleMatch(role="Data Scientist", score=0.8, matched_skills=["Python"], missing_skills=["Statistics"])]
    gaps = [GapAnalysis(role="Data Scientist", missing_skills=["Statistics"])]
    return profile, ats, matches, gaps


def test_explain_results_defaults_to_template_backend_with_no_backend_configured():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    explanation = explain_results(profile, ats, matches, gaps)

    assert explanation.source == "template"
    assert "70" in explanation.text
    assert "Data Scientist" in explanation.text


def test_explain_results_never_calls_the_llm_client_on_the_default_backend():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    explanation = explain_results(profile, ats, matches, gaps, client=_RaisingLLMClient())

    # Proves the template path never touches the client: if it did, the
    # RuntimeError below would propagate instead of being caught.
    assert explanation.source == "template"


def test_render_template_is_deterministic_for_the_same_input():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    first = render_template(profile, ats, matches, gaps)
    second = render_template(profile, ats, matches, gaps)

    assert first == second


def test_render_template_surfaces_failed_ats_checks():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    text = render_template(profile, ats, matches, gaps)

    assert "add a phone number" in text
    assert "contact_phone" not in text


def test_render_template_words_an_unknown_check_without_underscores():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()
    ats.checks.append(AtsCheck(name="file_format", passed=False, detail="Scanned image."))

    text = render_template(profile, ats, matches, gaps)

    assert "file format" in text
    assert "file_format" not in text


def test_render_template_shows_the_match_as_a_percentage():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    text = render_template(profile, ats, matches, gaps)

    assert "Data Scientist (80% match)" in text
    assert "0.8" not in text


def test_render_template_surfaces_top_match_and_missing_skills():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    text = render_template(profile, ats, matches, gaps)

    assert "Data Scientist" in text
    assert "Statistics" in text


def test_explain_results_falls_back_to_template_when_llm_backend_fails():
    # NFR-3.1: if the LLM API is unavailable, the system shall return
    # deterministic scores with the template explanation rather than
    # failing the request.
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    explanation = explain_results(profile, ats, matches, gaps, client=_RaisingLLMClient(), backend="llm")

    assert explanation.source == "template"
    assert explanation.text == render_template(profile, ats, matches, gaps)


def test_explain_results_uses_llm_backend_when_explicitly_requested(monkeypatch):
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    class _FakeLLMClient:
        def complete(self, system_prompt: str, user_prompt: str, **options) -> str:
            return "A coaching narrative."

    explanation = explain_results(profile, ats, matches, gaps, client=_FakeLLMClient(), backend="llm")

    assert explanation == ("A coaching narrative.", "llm")


def test_locked_template_names_the_domain_and_skips_role_lines():
    from app.models.schemas import DomainDetection
    from app.services.explainer import explain_results as _explain

    domain = DomainDetection(domain="healthcare", name="Healthcare & Life Sciences",
                             confidence=0.8, engine="llm")
    profile = ResumeProfile(name="Sam")
    ats = AtsScoreResponse(score=60, max_score=80, checks=[])

    explanation = _explain(profile, ats, [], [], backend="llm", domain=domain, locked=True,
                           lock_reason="community_edition")

    assert explanation.source == "template"
    assert "Healthcare & Life Sciences" in explanation.text
    assert "AI engine" in explanation.text and "Community Edition" in explanation.text
    assert "recommended role" not in explanation.text


def test_locked_template_wording_follows_the_lock_reason():
    from app.models.schemas import DomainDetection
    from app.services.explainer import render_template

    domain = DomainDetection(domain="healthcare", name="Healthcare & Life Sciences",
                             confidence=0.8, engine="llm")
    profile = ResumeProfile(name="Sam")
    ats = AtsScoreResponse(score=60, max_score=80, checks=[])

    community = render_template(profile, ats, [], [], domain, locked=True, lock_reason="community_edition")
    budget = render_template(profile, ats, [], [], domain, locked=True, lock_reason="ai_budget_exhausted")
    unknown = render_template(profile, ats, [], [], domain, locked=True, lock_reason="something_new")

    assert "Community Edition" in community and "upgrade" not in community.lower()
    assert "today's budget" in budget
    assert "not available on this analysis" in unknown


def test_llm_narrative_request_is_capped_and_lists_skills_plainly():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    class _Recording:
        def complete(self, system_prompt: str, user_prompt: str, **options) -> str:
            self.system_prompt, self.user_prompt, self.options = system_prompt, user_prompt, options
            return "narrative"

    client = _Recording()
    explain_results(profile, ats, matches, gaps, client=client, backend="llm")

    assert client.options == {"purpose": "narrate", "max_output_tokens": 600}
    assert "180 words" in client.system_prompt
    # Skills go in as plain comma lists, and the gaps block (a duplicate of
    # each match's missing list) is not repeated.
    assert "['" not in client.user_prompt
    assert "Skill gaps" not in client.user_prompt
    assert "missing Statistics" in client.user_prompt


def test_empty_llm_narrative_falls_back_to_the_template():
    profile, ats, matches, gaps = _profile_ats_matches_gaps()

    class _Empty:
        def complete(self, system_prompt: str, user_prompt: str, **options) -> str:
            return "   "

    explanation = explain_results(profile, ats, matches, gaps, client=_Empty(), backend="llm")

    assert explanation.source == "template"
