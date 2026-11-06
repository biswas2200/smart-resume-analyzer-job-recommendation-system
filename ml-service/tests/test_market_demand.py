"""services/market_demand.py and the weights hand-off. Embeddings are a
deterministic bag-of-words stub and the role catalogue is a small fixture,
so the tests are offline and the role assignment is predictable."""

import json
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import RankJob
from app.services import embeddings, fingerprint, market_demand, matcher, weights

client = TestClient(app)

CATALOGUE = [
    {"role": "Backend Engineer", "domain": "engineering", "skills": ["Java", "Kafka", "SQL", "Docker"]},
    {"role": "Data Analyst", "domain": "data_analytics", "skills": ["SQL", "Excel", "Tableau"]},
]


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
def _stubs(monkeypatch, tmp_path):
    monkeypatch.setattr(embeddings, "embed", _bag_of_words_embed)
    monkeypatch.setattr(matcher, "_load_roles", lambda: CATALOGUE)
    monkeypatch.setattr(weights, "WEIGHTS_SNAPSHOT_PATH", tmp_path / "weights_snapshot.json")
    weights._load_snapshot.cache_clear()
    matcher._role_vector.cache_clear()
    fingerprint.engine_fingerprint.cache_clear()
    yield
    weights._load_snapshot.cache_clear()
    matcher._role_vector.cache_clear()
    fingerprint.engine_fingerprint.cache_clear()


def backend_job(i: int, skills: list[str]) -> RankJob:
    return RankJob(id=f"b{i}", title="Backend Engineer", skills=skills)


JOBS = [
    backend_job(1, ["Java", "Kafka", "AWS"]),
    backend_job(2, ["Java", "Kafka"]),
    backend_job(3, ["Java", "SQL"]),
    backend_job(4, ["Java", "AWS"]),
    RankJob(id="d1", title="Data Analyst", skills=["SQL"]),  # only one job: below MIN_JOBS
    RankJob(id="x1", title="Chef", skills=["Cooking"]),  # no role close enough
]


def test_demand_is_the_share_of_a_roles_jobs_asking_for_each_skill():
    roles, unassigned = market_demand.market_demand(JOBS)

    assert [r.role for r in roles] == ["Backend Engineer"]
    backend = roles[0]
    assert backend.job_count == 4
    assert [(d.skill, d.share) for d in backend.in_demand] == [
        ("Java", 1.0), ("AWS", 0.5), ("Kafka", 0.5), ("SQL", 0.25)]
    assert unassigned == 2  # the lone Data Analyst job and the chef


def test_signals_cover_the_catalogue_skills_with_a_floor_of_half():
    [backend], _ = market_demand.market_demand(JOBS)

    # Java is the most asked (1.0); Kafka 0.5 of that -> 0.75; SQL 0.25 -> 0.625;
    # Docker is in the catalogue but no job asked -> the 0.5 floor. AWS is not a
    # catalogue skill, so it is shown as in demand but gets no signal.
    assert backend.signals == {"Java": 1.0, "Kafka": 0.75, "SQL": 0.625, "Docker": 0.5}


def test_abbreviated_titles_are_spelled_out_before_matching():
    assert market_demand.expand_title("SDE II - Payments") == "Software Development Engineer II - Payments"
    assert market_demand.expand_title("Senior SRE") == "Senior Site Reliability Engineer"
    assert market_demand.expand_title("Inside sales rep") == "Inside sales rep"


def test_an_installed_snapshot_is_used_by_the_next_match_and_the_fingerprint():
    before = matcher.match_roles(["Java", "Docker"], top_n=1)[0].score
    assert fingerprint.engine_fingerprint().weights_snapshot_id == "uniform"

    response = client.put("/weights-snapshot", json={
        "snapshotId": "2026-10-22T06:30:00Z", "createdAt": "2026-10-22T06:30:00Z", "sha256": "x",
        "weights": {"Backend Engineer": {"Java": 1.0, "Kafka": 0.1, "SQL": 0.1, "Docker": 1.0}}})

    assert response.status_code == 200
    assert response.json() == {"snapshot_id": "2026-10-22T06:30:00Z", "roles": 1}
    stored = json.loads(weights.WEIGHTS_SNAPSHOT_PATH.read_text())
    assert stored["snapshot_id"] == "2026-10-22T06:30:00Z"
    assert fingerprint.engine_fingerprint().weights_snapshot_id == "2026-10-22T06:30:00Z"
    after = matcher.match_roles(["Java", "Docker"], top_n=1)[0].score
    assert after > before  # the role now leans on the two skills this resume has


def test_market_demand_endpoint():
    response = client.post("/market-demand", json={"jobs": [j.model_dump() for j in JOBS]})
    assert response.status_code == 200
    body = response.json()
    assert body["roles"][0]["role"] == "Backend Engineer"
    assert body["unassigned_jobs"] == 2
