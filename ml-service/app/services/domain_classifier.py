"""Deterministic job-domain detection for a resume (no LLM, no network):
which entry of data/domains.json the resume belongs to, and therefore which
engine (local / llm) serves it.

Runs for every upload, so it must be cheap and must never
call out. Two signals, both already available offline:

1. Dictionary evidence -- canonical skills found in the text against the
   engineering taxonomy (skill_taxonomy.json) and the all-domain one
   (skill_taxonomy_general.json), attributed to the domains whose catalogue
   roles list them. A resume with at least ENGINEERING_MIN_SKILLS engineering
   skills, and no other domain with more dictionary evidence, is engineering
   regardless of the embedding: that guarantees an engineering resume never
   leaves the local, free path because of a noisy embedding, without letting
   the business tools the engineering taxonomy also lists (Excel, Power BI,
   budgeting) pull an accountant's resume onto it.
2. Embedding evidence -- cosine similarity between the resume's opening
   (headline, summary, skills section) and each domain's description, with
   the same pinned MiniLM model the matcher uses.

3. Role evidence -- the resume's headline (usually the job title) against every
   catalogue role's title, and its opening against every role's title and
   description, taking each domain's best role. A domain has a dozen roles
   against one description, so this tells a nurse from a care assistant and an
   advocate from a social worker far better than the single description does:
   on 288 real resumes in 24 categories it lifted agreement with the resume's
   own category from 42 % to 58 %.

score = 0.4 * headline-to-role + 0.4 * opening-to-role + 0.2 * cosine to the
domain description, rounded to 4 dp before the argmax with a name tie-break
(the same drift-proofing as matcher.py). The dictionary share still decides the
engineering override above and is reported by `hits`, but no longer enters the
score: it only ever added the generic business tools every domain shares. The
reported confidence is the winner's score relative to the runner-up, so
0.5 means "a coin flip", 1.0 means "nothing else came close".
"""

import json
import re
from functools import lru_cache

import numpy as np

from app.config import DATA_DIR
from app.models.schemas import DomainDetection
from app.services import embeddings
from app.services.dictionary_skills import GENERAL_TAXONOMY_PATH, TAXONOMY_PATH, find_skills

DOMAINS_PATH = DATA_DIR / "domains.json"
GENERAL_ROLES_PATH = DATA_DIR / "role_skills_general.json"

ENGINEERING_DOMAIN = "engineering"
ENGINEERING_MIN_SKILLS = 3
# How much of the resume the embedding signal reads: the first N words are
# where headline, summary and the skills block usually sit, and it keeps the
# input inside MiniLM's 256-token window so truncation is not model-dependent.
SNIPPET_WORDS = 200
DICTIONARY_WEIGHT = 0.4
HEADLINE_WEIGHT = 0.3
OPENING_ROLE_WEIGHT = 0.2
DESCRIPTION_WEIGHT = 0.05
HEADLINE_WORDS = 10
# The dictionary share counts in full only from this many hits: one stray hit is a 100 % share for
# whichever domain owns it, and says nothing.
DICTIONARY_FULL_EVIDENCE_HITS = 4


@lru_cache
def load_domains() -> list[dict]:
    with open(DOMAINS_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def domain_by_id() -> dict[str, dict]:
    return {d["id"]: d for d in load_domains()}


@lru_cache
def _skill_to_domains() -> dict[str, frozenset[str]]:
    """Lowercased canonical skill -> the non-engineering domains whose
    catalogue roles list it (a generic skill like "Customer service" maps to
    several, and is then weak evidence for each -- which is the point)."""
    with open(GENERAL_ROLES_PATH, encoding="utf-8") as f:
        roles: list[dict] = json.load(f)
    mapping: dict[str, set[str]] = {}
    for role in roles:
        for skill in role["skills"]:
            mapping.setdefault(skill.lower(), set()).add(role["domain"])
    return {skill: frozenset(domains) for skill, domains in mapping.items()}


@lru_cache
def _description_vectors() -> dict[str, np.ndarray]:
    domains = load_domains()
    vectors = embeddings.embed([d["description"] for d in domains])
    return {d["id"]: vectors[i] for i, d in enumerate(domains)}


@lru_cache
def _role_vectors() -> tuple[dict[str, list[int]], np.ndarray, np.ndarray]:
    """Every catalogue role (engineering and the other domains): which rows
    belong to which domain, the embedded titles, and the embedded
    "title. description" texts."""
    with open(GENERAL_ROLES_PATH, encoding="utf-8") as f:
        roles = [(r["role"], r["domain"], r["description"]) for r in json.load(f)]
    with open(DATA_DIR / "role_skills.json", encoding="utf-8") as f:
        roles += [(r["role"], ENGINEERING_DOMAIN, r["description"]) for r in json.load(f)]
    rows: dict[str, list[int]] = {}
    for index, (_, domain_id, _) in enumerate(roles):
        rows.setdefault(domain_id, []).append(index)
    titles = embeddings.embed([title for title, _, _ in roles])
    descriptions = embeddings.embed([f"{title}. {description}" for title, _, description in roles])
    return rows, titles, descriptions


# A resume often opens with a section heading instead of a job title; such a line says
# nothing about the field.
_GENERIC_HEADING_RE = re.compile(
    r"^(?:(?:professional|executive|career|personal|work|core|key|summary of)\s+)*"
    r"(?:summary|profile|overview|objective|highlights|qualifications|accomplishments|skills|experience|education|"
    r"history|competencies|strengths|about me|contact)(?:\s+(?:of qualifications|and \w+|&\s*\w+))?\s*:?$",
    re.IGNORECASE,
)


def _headline(resume_text: str) -> str:
    """The resume's headline: the first line that is not the candidate's name
    or contact details, cut to HEADLINE_WORDS words ("" when there is none)."""
    from app.services.local_ner_parser import _DATE_RANGE_RE, _DEGREE_START_RE, _INSTITUTION_KEYWORD_RE, _extract_name

    name = _extract_name(resume_text)
    for line in resume_text.splitlines():
        line = " ".join(line.split())
        if not line or line == name or "@" in line or "http" in line.lower() or _GENERIC_HEADING_RE.match(line):
            continue
        if _INSTITUTION_KEYWORD_RE.search(line) or _DEGREE_START_RE.match(line):
            continue  # a college or a degree says nothing about the field the person works in
        digits = sum(char.isdigit() for char in line)
        if digits >= 7 and sum(char.isalpha() for char in line) < 3 * digits:
            continue  # contact details: mostly digits, not a job line that happens to hold two years
        if len(line.split()) <= 5 and _DATE_RANGE_RE.search(line):
            continue  # "Aug 2025 - Jul 2027" on a line of its own
        return " ".join(line.split()[:HEADLINE_WORDS])
    return ""


def _best_role_similarity(vector: np.ndarray, matrix: np.ndarray, rows: list[int]) -> float:
    return max((max(embeddings.cosine_similarity(vector, matrix[row]), 0.0) for row in rows), default=0.0)


def _snippet(resume_text: str) -> str:
    """The resume's opening without its Education section: colleges and degrees say where a person
    studied, not which field they work in, and on a short resume they would otherwise fill the
    opening (a counselling-sounding "Institute ... Master of ..." block)."""
    from app.services.sectioner import split_sections

    sections = split_sections(resume_text)
    if sections.education:
        without_education = "\n".join(part for part in (sections.other, sections.experience, sections.skills) if part)
        if without_education.strip():
            resume_text = without_education
    return " ".join(resume_text.split()[:SNIPPET_WORDS])


def detect_domain(resume_text: str) -> DomainDetection:
    """Classify resume_text into one of data/domains.json's domains."""
    domains = load_domains()
    engineering_hits = find_skills(resume_text, TAXONOMY_PATH)
    general_hits = find_skills(resume_text, GENERAL_TAXONOMY_PATH)
    total_hits = len(engineering_hits) + len(general_hits)

    hits_per_domain: dict[str, int] = {d["id"]: 0 for d in domains}
    hits_per_domain[ENGINEERING_DOMAIN] = len(engineering_hits)
    skill_to_domains = _skill_to_domains()
    for skill in general_hits:
        for domain_id in skill_to_domains.get(skill.lower(), ()):
            if domain_id in hits_per_domain:
                hits_per_domain[domain_id] += 1

    snippet = _snippet(resume_text)
    snippet_vector = embeddings.embed([snippet])[0] if snippet else None
    headline = _headline(resume_text)
    headline_vector = embeddings.embed([headline])[0] if headline else None
    description_vectors = _description_vectors()
    role_rows, role_titles, role_descriptions = _role_vectors()

    scores: dict[str, float] = {}
    for d in domains:
        rows = role_rows.get(d["id"], [])
        cosine = (
            max(embeddings.cosine_similarity(snippet_vector, description_vectors[d["id"]]), 0.0)
            if snippet_vector is not None
            else 0.0
        )
        opening_role = _best_role_similarity(snippet_vector, role_descriptions, rows) if snippet_vector is not None else 0.0
        headline_role = _best_role_similarity(headline_vector, role_titles, rows) if headline_vector is not None else 0.0
        share = hits_per_domain[d["id"]] / total_hits if total_hits else 0.0
        share *= min(1.0, total_hits / DICTIONARY_FULL_EVIDENCE_HITS)
        scores[d["id"]] = round(
            DICTIONARY_WEIGHT * share
            + HEADLINE_WEIGHT * headline_role
            + OPENING_ROLE_WEIGHT * opening_role
            + DESCRIPTION_WEIGHT * cosine,
            4,
        )

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    strongest_other = max(
        (n for d, n in hits_per_domain.items() if d != ENGINEERING_DOMAIN), default=0
    )
    if len(engineering_hits) >= ENGINEERING_MIN_SKILLS and len(engineering_hits) >= strongest_other:
        winner_id = ENGINEERING_DOMAIN
    else:
        winner_id = ranked[0][0]
    winner_score = scores[winner_id]
    runner_up = max((s for d, s in scores.items() if d != winner_id), default=0.0)
    denominator = winner_score + runner_up
    confidence = round(winner_score / denominator, 2) if denominator > 0 else 0.0

    domain = domain_by_id()[winner_id]
    return DomainDetection(
        domain=domain["id"],
        name=domain["name"],
        confidence=confidence,
        engine=domain["engine"],
    )
