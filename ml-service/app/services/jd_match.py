"""JD-targeted match (FR-8.1/8.2): how well an already-extracted skill set
covers one pasted job description. Deterministic and offline, like the role
matcher it sits next to -- the JD's skills are found by dictionary matching
against both taxonomies (no LLM, no network), so the same JD and the same
resume always give the same score, and every point of it is explainable as
"you have these, you are missing those".

Score = 0.6 * coverage + 0.4 * similarity, rounded to 2 dp:
  coverage   -- share of the JD's recognised skills the candidate has
                exactly (what a recruiter's keyword screen measures);
  similarity -- cosine between the mean skill embeddings of the two sets,
                which gives partial credit for near-synonyms coverage
                misses ("PostgreSQL" against a JD that says "SQL").
The weights favour coverage because the missing list is the actionable
output; similarity keeps a resume with the right vocabulary from scoring
zero on a JD phrased differently.
"""

import re

import numpy as np

from app.models.schemas import JdMatchResponse, RoleMatch
from app.services import embeddings, matcher
from app.services.dictionary_skills import GENERAL_TAXONOMY_PATH, TAXONOMY_PATH, find_skills
from app.services.fingerprint import engine_fingerprint
from app.services.normalizer import normalize_skills

COVERAGE_WEIGHT = 0.6
SIMILARITY_WEIGHT = 0.4
# Only the top few appear in the explanation; the full lists are in the response.
EXPLAIN_LIMIT = 5

_SPACE_RUN = re.compile(r"[ \t\f\v]+")

# All-domain taxonomy entries (built from LinkedIn postings) that are also
# everyday job-ad words: "we are hiring", "design and build", "diversity,
# equity and inclusion", "competitive compensation". In a JD they are almost
# always that boilerplate rather than a requirement, so they are not counted
# as skills the JD asks for. Engineering-taxonomy hits are never filtered,
# and resumes are unaffected.
_JD_BOILERPLATE_SKILLS = frozenset(
    {"Hiring", "Design", "Inclusion", "Equity", "Compensation", "Recognition", "Trust"}
)


def extract_jd_skills(jd_text: str) -> list[str]:
    """Canonical skills a job description asks for: dictionary hits against
    the engineering taxonomy and the all-domain one, normalised together
    (engineering wins on collision, as everywhere else). Both taxonomies are
    always consulted -- an engineering JD asks for "Project Management" and
    a finance JD for "SQL" -- and the same normalisation is applied to the
    candidate's side in match_jd(), so the two sets compare like with like.
    """
    text = _SPACE_RUN.sub(" ", jd_text)
    general = [s for s in find_skills(text, GENERAL_TAXONOMY_PATH) if s not in _JD_BOILERPLATE_SKILLS]
    hits = [*find_skills(text, TAXONOMY_PATH), *general]
    return normalize_skills(hits, include_general=True)


def match_jd(candidate_skills: list[str], jd_text: str, domain: str = matcher.ENGINEERING_DOMAIN) -> JdMatchResponse:
    """Score `candidate_skills` (as the pipeline extracted them) against one
    job description. `domain` only chooses which catalogue the JD is
    compared to for the "closest role" hint; the score itself is between
    the resume and the JD alone.
    """
    jd_skills = extract_jd_skills(jd_text)
    candidate = normalize_skills(candidate_skills, include_general=True)
    candidate_set = set(candidate)

    matched = [s for s in jd_skills if s in candidate_set]
    missing = [s for s in jd_skills if s not in candidate_set]

    if jd_skills and candidate:
        coverage = len(matched) / len(jd_skills)
        similarity = max(
            embeddings.cosine_similarity(_mean_vector(candidate), _mean_vector(jd_skills)), 0.0
        )
    else:
        coverage = similarity = 0.0
    score = round(COVERAGE_WEIGHT * coverage + SIMILARITY_WEIGHT * similarity, 2)

    closest = matcher.match_roles(jd_skills, top_n=1, domain=domain)[0] if jd_skills else None

    return JdMatchResponse(
        score=score,
        coverage=round(coverage, 2),
        similarity=round(similarity, 2),
        jd_skills=jd_skills,
        matched_skills=matched,
        missing_skills=missing,
        closest_role=closest,
        explanation=_explain(jd_skills, matched, missing, coverage, closest),
        engine_fingerprint=engine_fingerprint(),
    )


def _mean_vector(skills: list[str]) -> np.ndarray:
    return embeddings.embed(skills).mean(axis=0)


def _explain(
    jd_skills: list[str],
    matched: list[str],
    missing: list[str],
    coverage: float,
    closest: RoleMatch | None,
) -> str:
    """Deterministic prose over the computed lists -- the JD-match
    counterpart of explainer.render_template, never an LLM."""
    if not jd_skills:
        return (
            "No skills we recognise were found in this job description. Paste the "
            "requirements or qualifications section, which usually names the tools and "
            "skills the role needs."
        )
    lines = [
        f"This job description asks for {len(jd_skills)} skills we recognise; your resume "
        f"covers {len(matched)} of them ({round(coverage * 100)}%)."
    ]
    if matched:
        lines.append("Strongest overlap: " + ", ".join(matched[:EXPLAIN_LIMIT]) + ".")
    if missing:
        lines.append("To target this role, add or evidence: " + ", ".join(missing[:EXPLAIN_LIMIT]) + ".")
    else:
        lines.append("Every recognised requirement is already on your resume.")
    if closest is not None:
        lines.append(f"The description reads like a {closest.role} role.")
    return "\n".join(lines)
