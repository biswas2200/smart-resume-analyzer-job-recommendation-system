"""Deterministic skill-to-role matching: embed the candidate's normalized
skill set and each curated role's required-skill set, then rank roles by
cosine similarity. Classic content-based filtering — no LLM involved, so the
score is reproducible and each match can be explained via matched/missing
skill lists.

Roles come from two catalogues: role_skills.json (engineering, curated by
hand) and role_skills_general.json (every other domain, built by
scripts/build_general_catalogue.py). A match always runs inside one domain
-- the one domain_classifier.py detected -- so an accountant is ranked
against finance roles, never against "Backend Software Engineer". The
default domain is engineering, which keeps this function's behaviour for
existing callers exactly what it was before the general catalogue existed.
"""

import json
from functools import lru_cache

import numpy as np

from app.config import DATA_DIR
from app.models.schemas import RoleMatch
from app.services import embeddings, weights
from app.services.normalizer import normalize_skills

ROLE_SKILLS_PATH = DATA_DIR / "role_skills.json"
GENERAL_ROLE_SKILLS_PATH = DATA_DIR / "role_skills_general.json"
ENGINEERING_DOMAIN = "engineering"


def _is_general(domain: str) -> bool:
    return domain != ENGINEERING_DOMAIN


@lru_cache
def _load_roles() -> list[dict]:
    """Every role from both catalogues, each tagged with its domain. Skills
    are normalized against the engineering taxonomy only for engineering
    roles (unchanged from before), and against both taxonomies for general
    ones, mirroring how the candidate's skills are normalized per domain in
    match_roles() so the two sides always compare like with like.
    """
    roles: list[dict] = []
    for path, default_domain in ((ROLE_SKILLS_PATH, ENGINEERING_DOMAIN), (GENERAL_ROLE_SKILLS_PATH, None)):
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for role in json.load(f):
                domain = role.get("domain") or default_domain
                if domain is None:
                    continue
                role["domain"] = domain
                role["skills"] = normalize_skills(role["skills"], include_general=_is_general(domain))
                roles.append(role)
    return roles


def _roles_in(domain: str) -> list[dict]:
    return [r for r in _load_roles() if r.get("domain", ENGINEERING_DOMAIN) == domain]


@lru_cache
def _role_vector(role_name: str, domain: str = ENGINEERING_DOMAIN) -> np.ndarray:
    """A role's skill-set vector, weighted by the active weights snapshot
    (FR-3.2): a role/skill pair with no EMA history yet is weighted 1.0 (see
    weights.py), so this is a plain mean whenever no snapshot has been
    shipped -- identical to the pre-weighting behavior.
    """
    roles = {r["role"]: r["skills"] for r in _roles_in(domain)}
    skills = roles[role_name]
    vectors = embeddings.embed(skills)
    skill_weights = np.array([weights.weight_for(role_name, skill) for skill in skills])
    if skill_weights.sum() <= 0:
        return vectors.mean(axis=0)
    return np.average(vectors, axis=0, weights=skill_weights)


def _skill_set_vector(skills: list[str]) -> np.ndarray:
    if not skills:
        return np.zeros(1)
    vectors = embeddings.embed(skills)
    return vectors.mean(axis=0)


def match_roles(raw_skills: list[str], top_n: int = 5, domain: str = ENGINEERING_DOMAIN) -> list[RoleMatch]:
    """Rank every curated role in `domain` against raw_skills by cosine
    similarity of their weighted skill-embedding vectors, returning the
    top_n highest-scoring matches with their matched/missing skill breakdown.

    Scores are rounded to 2 dp *before* sorting, and ties are broken by role
    name (FR-3.5): cross-CPU floating-point drift in the cosine product is on
    the order of 1e-5, which can flip which of two near-identical scores
    sorts first on a different machine -- rounding first means that drift
    never reaches the sort key, so ranking is stable across architectures
    (see docs/editions-and-parity.md §6, the PyTorch/ORT reproducibility
    sources).
    """
    candidate_skills = normalize_skills(raw_skills, include_general=_is_general(domain))
    candidate_set = set(candidate_skills)
    candidate_vector = _skill_set_vector(candidate_skills)

    scored: list[RoleMatch] = []
    for role in _roles_in(domain):
        role_skills = role["skills"]
        role_vector = _role_vector(role["role"], domain)

        score = embeddings.cosine_similarity(candidate_vector, role_vector)
        matched = [s for s in role_skills if s in candidate_set]
        missing = [s for s in role_skills if s not in candidate_set]

        scored.append(
            RoleMatch(
                role=role["role"],
                domain=domain,
                description=role.get("description", ""),
                score=round(score, 2),
                matched_skills=matched,
                missing_skills=missing,
            )
        )

    scored.sort(key=lambda m: (-m.score, m.role))
    return scored[:top_n]
