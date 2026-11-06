"""Job recommendations: which open jobs suit a resume, and why. Deterministic
and offline like the role matcher -- dictionary skill extraction and the
pinned MiniLM embedder, no LLM -- so the same resume and the same jobs always
rank the same way, and every score is explainable.

Each job's skills are extracted ONCE (extract_job_skills), when the backend
stores the posting, with the same extractor the JD match uses. Ranking then
compares those stored skills with the resume's:

  coverage   -- share of the job's skills the resume has exactly
                (what a recruiter's keyword screen measures);
  similarity -- cosine between the mean skill embeddings of the two sets
                (partial credit for near-synonyms: "PostgreSQL" vs "SQL");
  role_fit   -- how close the job title is to the candidate's best-matched
                catalogue roles (a "Backend Engineer" resume and an
                "SDE II - Payments" title).

score = 0.45 * coverage * evidence + 0.30 * similarity + 0.25 * role_fit,
where evidence = min(1, skills the job names / 5): a job naming only 3 skills
says little, and 2 of its 3 would otherwise count as 67% coverage and put a
kernels job first for a Java resume. A job whose description yielded no
skill we recognise is ranked on its title alone, at 0.5 * role_fit, so an
unreadable posting never outranks a well-matched one.
"""

import numpy as np

from app.models.schemas import JobSkills, JobText, RankedJob, RankJob
from app.services import embeddings
from app.services.jd_match import extract_jd_skills
from app.services.normalizer import normalize_skills

COVERAGE_WEIGHT = 0.45
SIMILARITY_WEIGHT = 0.30
ROLE_FIT_WEIGHT = 0.25
TITLE_ONLY_WEIGHT = 0.5
# A job naming fewer skills than this has its coverage counted proportionally less.
FULL_EVIDENCE_SKILLS = 5
EXPLAIN_LIMIT = 5
# Embeddings of skills and titles are reused across requests; this bounds the cache.
_CACHE_LIMIT = 50_000

_vector_cache: dict[str, np.ndarray] = {}

# Taxonomy entries that a full job posting almost always uses as ad copy, not
# as a requirement: soft skills every ad lists ("strong communication and
# leadership"), verbs that read as skills ("driving impact", "shipping
# features", "running in production"), perks ("yoga", "education
# allowance"), footer links ("follow us on Instagram") and equal-opportunity
# text ("protected by law"). Counted, they bloated every job's skill list and
# filled "skills to add" with them (first run, 22 Oct 2026: Communication in
# 175 of 489 jobs, Yoga in 31, Instagram in 38). Words that are a real
# requirement for some jobs (Sales, Operations, Testing, Social Media) stay.
# Pasted JDs (jd_match.py) keep the shorter list: they are usually just the
# requirements.
_JOB_AD_WORDS = frozenset({
    "Communication", "Communication skills", "Communications", "Interpersonal skills", "Leadership",
    "Collaboration", "Team Building", "Problem Solving", "Analytical Skills", "Attention to detail",
    "Creativity", "Storytelling", "Continuous Improvement", "Transparency", "Confidentiality",
    "Driving", "Shipping", "Production", "Discovery", "Onboarding", "Tooling",
    "Yoga", "Instagram", "Education", "Law",
})


def extract_job_skills(jobs: list[JobText]) -> list[JobSkills]:
    """The canonical skills each job asks for, from its title and text, minus job-ad copy."""
    return [JobSkills(id=job.id, skills=job_skills(f"{job.title}\n{job.text}")) for job in jobs]


def job_skills(text: str) -> list[str]:
    return [skill for skill in extract_jd_skills(text) if skill not in _JOB_AD_WORDS]


def rank_jobs(skills: list[str], roles: list[str], jobs: list[RankJob], top_n: int = 50) -> list[RankedJob]:
    """The `top_n` jobs best suited to a resume with `skills` whose
    best-matched catalogue roles are `roles`, best first (ties by id)."""
    candidate = normalize_skills(skills, include_general=True)
    candidate_set = set(candidate)
    _embed_missing([*candidate, *roles, *(job.title for job in jobs), *(s for job in jobs for s in job.skills)])

    candidate_vector = _mean(candidate)
    role_vectors = [(role, _vector_cache[role]) for role in roles if role in _vector_cache]

    ranked = [_score(job, candidate_set, candidate_vector, role_vectors) for job in jobs]
    ranked.sort(key=lambda job: (-job.score, job.id))
    return ranked[:top_n]


def clear_cache() -> None:
    _vector_cache.clear()


def _score(
    job: RankJob,
    candidate_set: set[str],
    candidate_vector: np.ndarray | None,
    role_vectors: list[tuple[str, np.ndarray]],
) -> RankedJob:
    matched = [s for s in job.skills if s in candidate_set]
    missing = [s for s in job.skills if s not in candidate_set]

    closest_role, role_fit = None, 0.0
    title_vector = _vector_cache[job.title] if job.title else None
    if title_vector is not None:
        for role, vector in role_vectors:
            fit = max(embeddings.cosine_similarity(title_vector, vector), 0.0)
            if fit > role_fit:
                closest_role, role_fit = role, fit

    if job.skills:
        coverage = len(matched) / len(job.skills)
        job_vector = _mean(job.skills)
        similarity = (
            max(embeddings.cosine_similarity(candidate_vector, job_vector), 0.0)
            if candidate_vector is not None and job_vector is not None
            else 0.0
        )
        evidence = min(1.0, len(job.skills) / FULL_EVIDENCE_SKILLS)
        score = COVERAGE_WEIGHT * coverage * evidence + SIMILARITY_WEIGHT * similarity + ROLE_FIT_WEIGHT * role_fit
    else:
        coverage = similarity = 0.0
        score = TITLE_ONLY_WEIGHT * role_fit

    return RankedJob(
        id=job.id,
        score=round(score, 2),
        coverage=round(coverage, 2),
        similarity=round(similarity, 2),
        role_fit=round(role_fit, 2),
        matched_skills=matched,
        missing_skills=missing,
        closest_role=closest_role,
        explanation=_explain(job, matched, missing, coverage, closest_role),
    )


def _explain(job: RankJob, matched: list[str], missing: list[str], coverage: float, closest_role: str | None) -> str:
    """Deterministic prose over the computed lists, never an LLM."""
    if not job.skills:
        line = "We couldn't read the skills this job asks for, so it is ranked on its title alone."
        return f"{line} The title is closest to your {closest_role} match." if closest_role else line
    lines = [
        f"You have {len(matched)} of the {len(job.skills)} skills this job asks for "
        f"({round(coverage * 100)}%)" + (": " + ", ".join(matched[:EXPLAIN_LIMIT]) + "." if matched else ".")
    ]
    if missing:
        lines.append("To add: " + ", ".join(missing[:EXPLAIN_LIMIT]) + ".")
    if closest_role:
        lines.append(f"The title is closest to your {closest_role} match.")
    return " ".join(lines)


def _embed_missing(texts: list[str]) -> None:
    missing = sorted({text for text in texts if text and text not in _vector_cache})
    if not missing:
        return
    if len(_vector_cache) + len(missing) > _CACHE_LIMIT:
        _vector_cache.clear()
    for text, vector in zip(missing, embeddings.embed(missing)):
        _vector_cache[text] = vector


def _mean(skills: list[str]) -> np.ndarray | None:
    vectors = [_vector_cache[s] for s in skills if s in _vector_cache]
    return np.mean(vectors, axis=0) if vectors else None
