"""services/job_rank.py -- job skill extraction and ranking. The embedding
model is stubbed (deterministic bag-of-words, as in test_jd_match.py) so the
tests run offline; the dictionary and normaliser side is real.
"""

import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import JobText, RankJob
from app.services import embeddings, jd_match, job_rank

client = TestClient(app)


def _bag_of_words_embed(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 64))
    for i, text in enumerate(texts):
        for word in text.lower().replace("-", " ").split():
            vectors[i, zlib.crc32(word.encode()) % 64] += 1.0
        norm = np.linalg.norm(vectors[i])
        if norm:
            vectors[i] /= norm
    return vectors


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed", _bag_of_words_embed)
    job_rank.clear_cache()
    yield
    job_rank.clear_cache()


BACKEND = RankJob(id="b", title="Backend Engineer", skills=["Java", "Spring Boot", "SQL", "Kafka"])
DATA = RankJob(id="d", title="Data Analyst", skills=["SQL", "Tableau", "Excel"])
SALES = RankJob(id="s", title="Account Executive", skills=["Salesforce", "Negotiation"])
UNREADABLE = RankJob(id="u", title="Backend Engineer II", skills=[])


def test_extracts_each_jobs_skills_from_title_and_text():
    [job] = job_rank.extract_job_skills(
        [JobText(id="1", title="Backend Engineer (Java)", text="You will build REST APIs with Spring Boot and PostgreSQL.")]
    )
    assert job.id == "1"
    for expected in ("Java", "Spring Boot", "PostgreSQL"):
        assert expected in job.skills, expected


AD_COPY = (
    "Backend Engineer. You will be shipping features in Java and driving impact in production. "
    "Strong communication and leadership skills. Perks: yoga, education allowance. "
    "Follow us on Instagram. We are an equal opportunity employer as required by law."
)
AD_WORDS = ("Shipping", "Driving", "Production", "Communication", "Leadership", "Yoga", "Education", "Instagram", "Law")


def test_job_ad_copy_is_not_counted_as_skills():
    # The plain JD extractor does find these words, so the filter is what removes them.
    unfiltered = jd_match.extract_jd_skills(AD_COPY)
    assert all(word in unfiltered for word in AD_WORDS)

    skills = job_rank.job_skills(AD_COPY)
    assert "Java" in skills
    for noise in AD_WORDS:
        assert noise not in skills, noise


def test_the_best_matched_job_ranks_first_with_its_reasons():
    ranked = job_rank.rank_jobs(
        ["Java", "Spring Boot", "SQL", "Docker"], ["Backend Engineer"], [SALES, DATA, BACKEND], top_n=3
    )

    assert [job.id for job in ranked] == ["b", "d", "s"]
    best = ranked[0]
    assert best.matched_skills == ["Java", "Spring Boot", "SQL"]
    assert best.missing_skills == ["Kafka"]
    assert best.coverage == 0.75
    assert best.closest_role == "Backend Engineer"
    assert "You have 3 of the 4 skills" in best.explanation
    assert "To add: Kafka." in best.explanation


def test_a_job_with_no_readable_skills_is_ranked_on_its_title_and_says_so():
    [job] = job_rank.rank_jobs(["Java"], ["Backend Engineer"], [UNREADABLE])

    assert job.coverage == 0.0 and job.similarity == 0.0
    assert job.score == round(job_rank.TITLE_ONLY_WEIGHT * job.role_fit, 2)
    assert job.score > 0
    assert job.explanation.startswith("We couldn't read the skills")


def test_an_unreadable_posting_never_outranks_a_well_matched_one():
    ranked = job_rank.rank_jobs(["Java", "Spring Boot", "SQL", "Kafka"], ["Backend Engineer"], [UNREADABLE, BACKEND])
    assert [job.id for job in ranked] == ["b", "u"]


def test_a_job_naming_few_skills_cannot_win_on_coverage_alone():
    thin = RankJob(id="t", title="Performance Engineer", skills=["REST APIs", "Machine Learning", "Git"])
    full = RankJob(id="f", title="Performance Engineer",
                   skills=["Java", "Spring Boot", "SQL", "Docker", "Kafka", "AWS"])
    resume = ["Java", "Spring Boot", "SQL", "Docker", "REST APIs", "Git"]

    ranked = job_rank.rank_jobs(resume, [], [thin, full])

    assert [job.id for job in ranked] == ["f", "t"]
    thin_result = ranked[1]
    assert thin_result.coverage == 0.67  # still reported as-is in the reasons
    assert "2 of the 3 skills" in thin_result.explanation


def test_ranking_is_deterministic_and_ties_break_by_id():
    twin_a = RankJob(id="a", title="Data Analyst", skills=["SQL", "Tableau", "Excel"])
    first = job_rank.rank_jobs(["SQL"], [], [DATA, twin_a])
    second = job_rank.rank_jobs(["SQL"], [], [twin_a, DATA])
    assert [j.id for j in first] == [j.id for j in second] == ["a", "d"]


def test_no_resume_skills_and_no_roles_scores_zero_without_failing():
    [job] = job_rank.rank_jobs([], [], [BACKEND])
    assert job.score == 0.0
    assert job.missing_skills == BACKEND.skills


def test_endpoints_round_trip():
    extracted = client.post(
        "/extract-job-skills", json={"jobs": [{"id": "1", "title": "Data Analyst", "text": "SQL and Tableau dashboards"}]}
    )
    assert extracted.status_code == 200
    assert "SQL" in extracted.json()["jobs"][0]["skills"]

    ranked = client.post(
        "/rank-jobs",
        json={"skills": ["SQL"], "roles": ["Data Analyst"], "top_n": 1,
              "jobs": [{"id": "d", "title": "Data Analyst", "skills": ["SQL", "Tableau"]},
                       {"id": "s", "title": "Account Executive", "skills": ["Salesforce"]}]},
    )
    assert ranked.status_code == 200
    body = ranked.json()
    assert [j["id"] for j in body["jobs"]] == ["d"]
    assert "engine_fingerprint" in body
