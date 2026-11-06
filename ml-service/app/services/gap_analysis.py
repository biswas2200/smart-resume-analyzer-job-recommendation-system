"""Deterministic skill-gap analysis: for each top-matched role, surface the
required skills the candidate doesn't have yet. Derived directly from
matcher.py's output — no LLM involved.
"""

from app.models.schemas import GapAnalysis, RoleMatch


def analyze_gaps(matches: list[RoleMatch]) -> list[GapAnalysis]:
    return [GapAnalysis(role=m.role, missing_skills=m.missing_skills) for m in matches]
