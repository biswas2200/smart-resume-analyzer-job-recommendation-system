"""Turns already-computed scores/matches into a readable explanation. Two
backends, selected by Settings.explainer_backend (default "template", per
FR-5.4): TemplateExplainer composes deterministic, network-free prose from
the already-computed data; the LLM backend asks a coaching-framed model for a
more polished narrative. Neither ever rewrites resume content or influences
the underlying score (FR-5.3) -- the LLM backend is opt-in, since it
costs money, needs network access, and (unlike the template) is not
reproducible for the same input.
"""

import logging
from typing import NamedTuple

from app.config import get_settings
from app.models.schemas import AtsScoreResponse, DomainDetection, GapAnalysis, ResumeProfile, RoleMatch
from app.services.ats_score import MIN_WORD_COUNT
from app.services.llm_client import LLMClient, get_llm_client

log = logging.getLogger(__name__)

# The word bound is a cost control: output tokens are the expensive side,
# and "short paragraphs" alone lets the model run to twice this length.
SYSTEM_PROMPT = (
    "You are a career coach explaining resume analysis results to a "
    "candidate. You are given pre-computed scores, role matches, and skill "
    "gaps -- do not recompute or second-guess them, and do not rewrite any "
    "resume content. Write exactly 3 short paragraphs, 180 words in total at "
    "most: (1) what the ATS score means and the single biggest thing to fix "
    "about it, (2) the top matched role and why it fits, (3) the most "
    "impactful skill gaps to close next. Be specific, encouraging, and "
    "concise. Plain text only, no headings or bullet points."
)


def _build_user_prompt(
    profile: ResumeProfile,
    ats_score: AtsScoreResponse,
    matches: list[RoleMatch],
    gaps: list[GapAnalysis],
    domain: DomainDetection | None = None,
) -> str:
    lines = [
        f"Candidate: {profile.name or 'Unknown'}",
        *([f"Field: {domain.name}"] if domain else []),
        f"ATS score: {ats_score.score}/{ats_score.max_score}",
        "Failed ATS checks: "
        + (", ".join(c.name for c in ats_score.checks if not c.passed) or "none"),
        "",
        "Top role matches:",
    ]
    for m in matches:
        lines.append(
            f"- {m.role} (score {m.score}): matched {_join(m.matched_skills)}; "
            f"missing {_join(m.missing_skills)}"
        )
    return "\n".join(lines)


def _join(skills: list[str]) -> str:
    # Plain comma lists, not Python reprs -- fewer quote/bracket tokens.
    return ", ".join(skills) if skills else "none"


class Explanation(NamedTuple):
    """An explanation's text plus which backend actually produced it
    (explanation_source) -- routers surface both, since FR-5.4 requires the
    LLM narrative to be labelled as non-deterministic rather than presented
    the same way as the template.
    """

    text: str
    source: str  # "template" | "llm"


# One sentence per lock reason (schemas.LockReason), appended after the ATS
# line of a locked result in place of the role lines. Keyed so the copy
# never claims "upgrade" to a Community Edition user who has nothing to
# upgrade to.
LOCKED_MESSAGES = {
    "community_edition": (
        "Your resume reads as {domain}. Role recommendations and skill gaps for this "
        "field need the AI engine, which the Community Edition does not include -- "
        "use the cloud version for this resume."
    ),
    "ai_budget_exhausted": (
        "Your resume reads as {domain}. The AI engine has reached today's budget "
        "-- try again tomorrow."
    ),
}
# What to do about each failed ATS check (ats_score.BASE_CHECK_WEIGHTS), in
# the user's words -- the check names themselves are identifiers, not copy.
# A check added later without an entry here falls back to its name with the
# underscores spaced out, never to a raw identifier.
_CHECK_ADVICE = {
    "contact_email": "add an email address",
    "contact_phone": "add a phone number",
    "section_experience": "add an Experience section",
    "section_education": "add an Education section",
    "section_skills": "add a Skills section",
    "sufficient_length": f"add more detail, since your resume is shorter than {MIN_WORD_COUNT} words",
    "no_hidden_text": "remove the hidden (white, tiny or off-page) text, which was ignored",
}

_DEFAULT_LOCKED_MESSAGE = (
    "Your resume reads as {domain}. Role recommendations and skill gaps for this "
    "field are not available on this analysis."
)


def render_template(
    profile: ResumeProfile,
    ats_score: AtsScoreResponse,
    matches: list[RoleMatch],
    gaps: list[GapAnalysis],
    domain: DomainDetection | None = None,
    locked: bool = False,
    lock_reason: str | None = None,
) -> str:
    """Deterministic explanation, no model call: composes the same three
    points the LLM prompt below asks for (ATS headline, top match, key
    gaps) purely from already-computed data, so switching explainer backends
    changes only how polished the wording is, never what information is
    covered. When `locked` (the domain needed the AI engine and this
    request could not use it) the role lines are replaced by one sentence
    saying why, chosen by `lock_reason` (LOCKED_MESSAGES).
    """
    advice = [
        _CHECK_ADVICE.get(c.name, c.name.replace("_", " ")) for c in ats_score.checks if not c.passed
    ]
    lines = [
        f"Your ATS compatibility score is {ats_score.score:g}/{ats_score.max_score:g}."
        + (
            f" To raise it: {'; '.join(advice)}."
            if advice
            else " All checked ATS factors passed."
        )
    ]

    if locked and domain is not None:
        message = LOCKED_MESSAGES.get(lock_reason or "", _DEFAULT_LOCKED_MESSAGE)
        lines.append(message.format(domain=domain.name))
        return "\n".join(lines)

    if matches:
        top = matches[0]
        matched = ", ".join(top.matched_skills) if top.matched_skills else "no skills in common yet"
        lines.append(
            f"Your top recommended role is {top.role} ({round(top.score * 100)}% match), "
            f"based on matched skills: {matched}."
        )

    top_gap = next((g for g in gaps if g.missing_skills), None)
    if top_gap is not None:
        lines.append(
            f"To strengthen your match for {top_gap.role}, focus next on: "
            f"{', '.join(top_gap.missing_skills)}."
        )

    return "\n".join(lines)


def explain_results(
    profile: ResumeProfile,
    ats_score: AtsScoreResponse,
    matches: list[RoleMatch],
    gaps: list[GapAnalysis],
    client: LLMClient | None = None,
    backend: str | None = None,
    domain: DomainDetection | None = None,
    locked: bool = False,
    lock_reason: str | None = None,
) -> Explanation:
    """Explains the already-computed results via the resolved backend
    (`backend`, falling back to Settings.explainer_backend). If the LLM
    backend is selected but fails for any reason -- including
    LLMUnavailableError when ADC/project aren't configured -- falls back to
    the deterministic template instead of failing the request (NFR-3.1: LLM
    unavailability must never prevent a candidate from getting their score).
    A locked result never goes near the LLM: there is nothing to narrate.
    """
    resolved_backend = backend or get_settings().explainer_backend
    if locked or resolved_backend != "llm":
        return Explanation(
            text=render_template(profile, ats_score, matches, gaps, domain, locked, lock_reason),
            source="template",
        )

    try:
        llm = client or get_llm_client()
        user_prompt = _build_user_prompt(profile, ats_score, matches, gaps, domain)
        text = llm.complete(
            SYSTEM_PROMPT,
            user_prompt,
            purpose="narrate",
            max_output_tokens=get_settings().llm_narrate_max_output_tokens,
        ).strip()
        if text:
            return Explanation(text=text, source="llm")
        log.warning("LLM narrative came back empty; using the template")
    except Exception as exc:
        # Logged, not raised: NFR-3.1. But never silently -- a quota or
        # auth problem here is a cost/ops signal someone needs to see.
        log.warning("LLM narrative failed, using the template: %s", exc)
    return Explanation(text=render_template(profile, ats_score, matches, gaps, domain), source="template")
