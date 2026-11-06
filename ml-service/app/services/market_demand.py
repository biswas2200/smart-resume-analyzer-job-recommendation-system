"""Job-market demand: which skills open jobs ask for, per catalogue role --
the "job-market data" signal SRS FR-7 always planned for the EMA skill
weights, alongside user feedback.

1. Each job is assigned to the catalogue role its title is closest to
   (MiniLM cosine of the title against every role name, both catalogues),
   if that similarity is at least ASSIGN_THRESHOLD; common abbreviations
   are spelled out first ("SDE II" -> "Software Development Engineer II").
   Measured on 489 live Bengaluru jobs (22 Oct 2026): 0.6 assigned 303 jobs
   with few wrong roles; 0.5 assigned more but "Associate Compliance
   Manager" became "Administrative Assistant".
2. A role with at least MIN_JOBS assigned jobs gets its demand: the share of
   its jobs asking for each skill.
3. That demand becomes one EMA signal per skill in the role's catalogue
   entry: 0.5 + 0.5 * share / (the role's most-asked share). The most
   in-demand skill signals 1.0; a catalogue skill no job asked for signals
   0.5, so over repeated days it fades towards half weight, never to zero --
   a small sample of jobs can down-weight a skill but never delete it.
"""

import re

import numpy as np

from app.models.schemas import RankJob, RoleDemand, SkillDemand
from app.services import embeddings, matcher

ASSIGN_THRESHOLD = 0.6
MIN_JOBS = 3
IN_DEMAND_LIMIT = 15
SIGNAL_FLOOR = 0.5

_ABBREVIATIONS = (
    (re.compile(r"\bSDE\b", re.IGNORECASE), "Software Development Engineer"),
    (re.compile(r"\bSWE\b", re.IGNORECASE), "Software Engineer"),
    (re.compile(r"\bSRE\b", re.IGNORECASE), "Site Reliability Engineer"),
    (re.compile(r"\bSDET\b", re.IGNORECASE), "Software Development Engineer in Test"),
    (re.compile(r"\bML\b"), "Machine Learning"),
    (re.compile(r"\bQA\b"), "Quality Assurance"),
)


def expand_title(title: str) -> str:
    for pattern, words in _ABBREVIATIONS:
        title = pattern.sub(words, title)
    return title


def market_demand(jobs: list[RankJob]) -> tuple[list[RoleDemand], int]:
    """Per-role demand and EMA signals, roles with the most jobs first (ties
    by name); plus how many jobs matched no role."""
    roles = matcher._load_roles()
    titled = [job for job in jobs if job.title.strip()]
    if not roles or not titled:
        return [], len(jobs)

    role_vectors = embeddings.embed([role["role"] for role in roles])
    title_vectors = embeddings.embed([expand_title(job.title) for job in titled])
    similarity = _normalise(title_vectors) @ _normalise(role_vectors).T
    best = similarity.argmax(axis=1)

    assigned: dict[int, list[RankJob]] = {}
    unassigned = len(jobs) - len(titled)
    for job, index, score in zip(titled, best, similarity.max(axis=1)):
        if score >= ASSIGN_THRESHOLD:
            assigned.setdefault(int(index), []).append(job)
        else:
            unassigned += 1

    demands = []
    for index, role_jobs in assigned.items():
        if len(role_jobs) < MIN_JOBS:
            unassigned += len(role_jobs)
            continue
        role = roles[index]
        demands.append(_role_demand(role, role_jobs))
    demands.sort(key=lambda demand: (-demand.job_count, demand.role))
    return demands, unassigned


def _role_demand(role: dict, jobs: list[RankJob]) -> RoleDemand:
    counts: dict[str, int] = {}
    for job in jobs:
        for skill in set(job.skills):
            counts[skill] = counts.get(skill, 0) + 1
    shares = {skill: count / len(jobs) for skill, count in counts.items()}
    top_share = max(shares.values(), default=0.0)

    in_demand = sorted(shares.items(), key=lambda item: (-item[1], item[0]))[:IN_DEMAND_LIMIT]
    signals = {
        skill: round(SIGNAL_FLOOR + (1 - SIGNAL_FLOOR) * (shares.get(skill, 0.0) / top_share if top_share else 0.0), 3)
        for skill in role["skills"]
    }
    return RoleDemand(
        role=role["role"],
        domain=role.get("domain", matcher.ENGINEERING_DOMAIN),
        job_count=len(jobs),
        in_demand=[SkillDemand(skill=skill, share=round(share, 2)) for skill, share in in_demand],
        signals=signals,
    )


def _normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms
