"""Deterministic skill normalization — maps raw skill strings to a canonical
taxonomy. No LLM involved: this is a plain lookup table, kept explainable and
reproducible so match scores can be traced back to exact skill matches.
"""

import json
from functools import lru_cache

from app.config import DATA_DIR

TAXONOMY_PATH = DATA_DIR / "skill_taxonomy.json"
GENERAL_TAXONOMY_PATH = DATA_DIR / "skill_taxonomy_general.json"


@lru_cache
def _variant_to_canonical(include_general: bool = False) -> dict[str, str]:
    """Lookup from lowercased variant to canonical name. The engineering
    taxonomy is always loaded; the all-domain one only when asked for, and
    an engineering entry wins any collision, so enabling it can never change
    how an engineering skill normalizes.
    """
    paths = [TAXONOMY_PATH] + ([GENERAL_TAXONOMY_PATH] if include_general else [])
    lookup: dict[str, str] = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            canonical_to_variants: dict[str, list[str]] = json.load(f)
        for canonical, variants in canonical_to_variants.items():
            lookup.setdefault(canonical.strip().lower(), canonical)
            for variant in variants:
                lookup.setdefault(variant.strip().lower(), canonical)
    return lookup


def normalize_skill(raw_skill: str, include_general: bool = False) -> str:
    """Map a single raw skill string to its canonical form. Skills not found
    in the taxonomy are returned title-cased and unchanged otherwise, since
    they may be legitimate skills the taxonomy hasn't been curated for yet.
    """
    key = raw_skill.strip().lower()
    if not key:
        return ""
    return _variant_to_canonical(include_general).get(key, raw_skill.strip())


def normalize_skills(raw_skills: list[str], include_general: bool = False) -> list[str]:
    """Normalize a list of raw skill strings, de-duplicating while
    preserving first-seen order. `include_general=True` also canonicalizes
    against the all-domain taxonomy -- used only on the non-engineering
    (AI-engine) path, so the engineering path's output is unchanged.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_skills:
        normalized = normalize_skill(raw, include_general)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
