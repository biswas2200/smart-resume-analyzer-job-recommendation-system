"""Deterministic ATS (Applicant Tracking System) compatibility score.
Pure rule-based checks over the resume text — no LLM, no embeddings — so the
score is explainable line-by-line: every point gained or lost maps to one
named check.
"""

import re

from app.models.schemas import AtsCheck, AtsScoreResponse

# Local part and domain are each exactly one unbounded character class,
# never two adjacent/nested ones -- this text comes straight from
# user-uploaded resumes, so avoiding any backtracking-blowup shape matters
# more than rejecting a domain with no dot in it (an edge case this lenient,
# heuristic check doesn't need to catch anyway).
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{8,}\d)")

SECTION_HEADERS = {
    "experience": ["experience", "work experience", "employment history"],
    "education": ["education", "academic background"],
    "skills": ["skills", "technical skills", "core competencies"],
}

MIN_WORD_COUNT = 150

BASE_CHECK_WEIGHTS = {
    "contact_email": 15.0,
    "contact_phone": 10.0,
    "section_experience": 15.0,
    "section_education": 15.0,
    "section_skills": 15.0,
    "sufficient_length": 10.0,
    "no_hidden_text": 10.0,
}
KEYWORD_WEIGHT = 20.0


def _has_section(text_lower: str, header_variants: list[str]) -> bool:
    return any(variant in text_lower for variant in header_variants)


def score_resume(
    resume_text: str, target_keywords: list[str] | None = None, hidden_word_count: int = 0
) -> AtsScoreResponse:
    """Run every rule-based check against resume_text and total their weights.
    When target_keywords is given, an extra "keyword_coverage" check is added
    on top of the base checks (and its weight added to max_score) -- omitted
    entirely otherwise, since without target keywords there's nothing to
    check coverage against. `hidden_word_count` is how many words the file
    extractor left out as unreadable (document_extraction.ExtractedText);
    real ATS tools flag hidden text as keyword stuffing, so any fails
    "no_hidden_text". Text sent as JSON has no file to inspect, so it passes.
    """
    text_lower = resume_text.lower()
    checks: list[AtsCheck] = []
    earned = 0.0
    max_score = sum(BASE_CHECK_WEIGHTS.values())

    has_email = bool(EMAIL_RE.search(resume_text))
    checks.append(AtsCheck(
        name="contact_email",
        passed=has_email,
        detail="Email address found" if has_email else "No parseable email address found",
    ))
    earned += BASE_CHECK_WEIGHTS["contact_email"] if has_email else 0.0

    has_phone = bool(PHONE_RE.search(resume_text))
    checks.append(AtsCheck(
        name="contact_phone",
        passed=has_phone,
        detail="Phone number found" if has_phone else "No parseable phone number found",
    ))
    earned += BASE_CHECK_WEIGHTS["contact_phone"] if has_phone else 0.0

    for key, variants in SECTION_HEADERS.items():
        check_name = f"section_{key}"
        present = _has_section(text_lower, variants)
        checks.append(AtsCheck(
            name=check_name,
            passed=present,
            detail=f"'{key.title()}' section header found" if present else f"No '{key.title()}' section header found",
        ))
        earned += BASE_CHECK_WEIGHTS[check_name] if present else 0.0

    word_count = len(resume_text.split())
    long_enough = word_count >= MIN_WORD_COUNT
    checks.append(AtsCheck(
        name="sufficient_length",
        passed=long_enough,
        detail=f"{word_count} words (minimum {MIN_WORD_COUNT})",
    ))
    earned += BASE_CHECK_WEIGHTS["sufficient_length"] if long_enough else 0.0

    no_hidden_text = hidden_word_count == 0
    checks.append(AtsCheck(
        name="no_hidden_text",
        passed=no_hidden_text,
        detail="No hidden text found" if no_hidden_text
        else f"{hidden_word_count} words of hidden text (white, tiny or off-page) were ignored",
    ))
    earned += BASE_CHECK_WEIGHTS["no_hidden_text"] if no_hidden_text else 0.0

    if target_keywords:
        matched_keywords = [kw for kw in target_keywords if kw.lower() in text_lower]
        coverage = len(matched_keywords) / len(target_keywords)
        checks.append(AtsCheck(
            name="keyword_coverage",
            passed=coverage >= 0.5,
            detail=f"{len(matched_keywords)}/{len(target_keywords)} target keywords found in resume",
        ))
        earned += KEYWORD_WEIGHT * coverage
        max_score += KEYWORD_WEIGHT

    return AtsScoreResponse(score=round(earned, 2), max_score=round(max_score, 2), checks=checks)
