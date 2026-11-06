"""services/jd_match.py -- the JD-targeted match. The embedding model is
stubbed (deterministic bag-of-words) so the tests run offline and in
milliseconds; the dictionary/normaliser side is real.
"""

import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import embeddings, jd_match, matcher

client = TestClient(app)

BACKEND_JD = """
Backend Software Engineer

Requirements:
- 4+ years with Java and Spring Boot building REST APIs
- Strong SQL (PostgreSQL) and experience with Docker and Kubernetes
- Familiarity with AWS and CI/CD; Git workflows
- Excellent communication and project management skills
"""


def _bag_of_words_embed(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 64))
    for i, text in enumerate(texts):
        for word in text.lower().split():
            vectors[i, zlib.crc32(word.encode()) % 64] += 1.0
        norm = np.linalg.norm(vectors[i])
        if norm:
            vectors[i] /= norm
    return vectors


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed", _bag_of_words_embed)
    matcher._role_vector.cache_clear()
    yield
    matcher._role_vector.cache_clear()


def test_extracts_canonical_skills_from_a_jd_across_both_taxonomies():
    skills = jd_match.extract_jd_skills(BACKEND_JD)

    for expected in ("Java", "Spring Boot", "SQL", "PostgreSQL", "Docker", "Kubernetes", "AWS", "Git"):
        assert expected in skills, expected
    assert "Project Management" in skills  # general taxonomy
    assert len(skills) == len(set(skills))  # deduplicated


def test_job_ad_boilerplate_words_are_not_counted_as_skills():
    jd = (
        "We are hiring a backend engineer to design and build microservices with Kafka, "
        "Redis, GraphQL and FastAPI. We value diversity, equity and inclusion and offer "
        "competitive compensation."
    )

    skills = jd_match.extract_jd_skills(jd)

    for expected in ("Microservices", "Kafka", "Redis", "GraphQL", "FastAPI"):
        assert expected in skills, expected
    for boilerplate in ("Hiring", "Design", "Equity", "Inclusion", "Compensation"):
        assert boilerplate not in skills, boilerplate


def test_full_coverage_scores_high_and_lists_no_missing_skills():
    jd_skills = jd_match.extract_jd_skills(BACKEND_JD)

    result = jd_match.match_jd(jd_skills, BACKEND_JD, domain="engineering")

    assert result.coverage == 1.0
    assert result.missing_skills == []
    assert result.matched_skills == jd_skills
    assert result.score >= 0.9
    assert result.closest_role is not None and result.closest_role.domain == "engineering"
    assert "covers" in result.explanation and "Every recognised requirement" in result.explanation


def test_partial_coverage_lists_what_is_missing_first_in_the_explanation():
    result = jd_match.match_jd(["Java", "Spring Boot", "SQL"], BACKEND_JD)

    assert 0 < result.coverage < 1
    assert set(result.matched_skills) == {"Java", "Spring Boot", "SQL"}
    assert "Docker" in result.missing_skills and "Kubernetes" in result.missing_skills
    assert "To target this role, add or evidence:" in result.explanation
    # coverage/similarity are themselves rounded in the response, so allow 1 dp of slack.
    assert result.score == pytest.approx(0.6 * result.coverage + 0.4 * result.similarity, abs=0.011)


def test_candidate_skills_are_normalised_before_comparison():
    # Variants and case fold onto the canonical names the JD side uses.
    result = jd_match.match_jd(["java", "spring boot", "postgres"], BACKEND_JD)

    assert "Java" in result.matched_skills and "Spring Boot" in result.matched_skills
    assert "PostgreSQL" in result.matched_skills


def test_a_jd_with_no_recognised_skills_scores_zero_and_says_so():
    result = jd_match.match_jd(["Java"], "We are a friendly team looking for a great colleague.")

    assert result.score == 0.0 and result.jd_skills == [] and result.closest_role is None
    assert "No skills we recognise" in result.explanation


def test_same_input_gives_the_same_output():
    first = jd_match.match_jd(["Java", "SQL"], BACKEND_JD)
    second = jd_match.match_jd(["Java", "SQL"], BACKEND_JD)

    assert first == second


def test_match_jd_endpoint_round_trips_and_validates_length():
    response = client.post("/match-jd", json={"skills": ["Java", "SQL"], "jd_text": BACKEND_JD})

    assert response.status_code == 200
    body = response.json()
    assert {"score", "coverage", "similarity", "jd_skills", "matched_skills", "missing_skills",
            "closest_role", "explanation", "engine_fingerprint"} <= body.keys()
    assert body["engine_fingerprint"]["engine_version"] == "0.5.5"

    assert client.post("/match-jd", json={"skills": [], "jd_text": ""}).status_code == 422
    assert client.post("/match-jd", json={"skills": [], "jd_text": "x" * 20_001}).status_code == 422


def test_non_engineering_jd_uses_that_domains_catalogue_for_the_closest_role():
    jd = "Registered Nurse needed: Patient Care, Medication Administration, ACLS, BLS, Patient Education, Epic."
    result = jd_match.match_jd(["Patient Care", "ACLS", "BLS"], jd, domain="healthcare")

    assert result.closest_role is not None and result.closest_role.domain == "healthcare"
    assert "ACLS" in result.matched_skills
