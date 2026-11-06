"""Note: matcher.py loads a sentence-transformers model on first use, which
requires downloading model weights the first time it's run on a machine
(then caches locally). These tests need network access for that first
download; they are otherwise deterministic and need no API key.

The rounding/tie-break/weighting tests below are the exception: they
monkeypatch embeddings.embed/cosine_similarity directly, so they need no
model download and stay deterministic regardless of what a real embedding
would produce (FR-3.2/FR-3.5).
"""

import numpy as np

from app.services import embeddings, matcher, weights
from app.services.matcher import match_roles


def test_backend_skills_match_backend_role_highest():
    matches = match_roles(
        ["Java", "Spring Boot", "SQL", "REST APIs", "Docker", "Microservices"],
        top_n=3,
    )
    assert matches[0].role == "Backend Software Engineer"
    assert matches[0].score >= matches[-1].score


def test_matched_and_missing_skills_partition_role_requirements():
    matches = match_roles(["Figma", "User Research", "Wireframing"], top_n=1)
    top = matches[0]
    assert top.role == "UX/UI Designer"
    assert set(top.matched_skills) <= {"Figma", "User Research", "Wireframing", "Prototyping", "Interaction Design", "Usability Testing"}
    assert "Prototyping" in top.missing_skills


def test_top_n_limits_result_count():
    matches = match_roles(["Python"], top_n=2)
    assert len(matches) == 2


def test_scores_are_rounded_to_two_decimal_places_before_sorting(monkeypatch):
    monkeypatch.setattr(matcher, "_load_roles", lambda: [{"role": "Role A", "skills": ["Alpha"]}])
    monkeypatch.setattr(embeddings, "embed", lambda skills: np.ones((len(skills), 1)))
    monkeypatch.setattr(embeddings, "cosine_similarity", lambda a, b: 0.8666666)
    matcher._role_vector.cache_clear()

    matches = match_roles(["Alpha"], top_n=1)

    assert matches[0].score == 0.87
    matcher._role_vector.cache_clear()


def test_ties_are_broken_by_role_name(monkeypatch):
    # FR-3.5: with identical rounded scores, ranking must still be
    # deterministic -- alphabetical by role name -- rather than depending on
    # sort stability against whatever order the roles happened to load in.
    monkeypatch.setattr(
        matcher,
        "_load_roles",
        lambda: [
            {"role": "Zeta Role", "skills": ["Alpha"]},
            {"role": "Alpha Role", "skills": ["Alpha"]},
            {"role": "Mid Role", "skills": ["Alpha"]},
        ],
    )
    monkeypatch.setattr(embeddings, "embed", lambda skills: np.ones((len(skills), 1)))
    monkeypatch.setattr(embeddings, "cosine_similarity", lambda a, b: 0.5)
    matcher._role_vector.cache_clear()

    matches = match_roles(["Alpha"], top_n=3)

    assert [m.role for m in matches] == ["Alpha Role", "Mid Role", "Zeta Role"]
    matcher._role_vector.cache_clear()


def test_role_vector_is_weighted_by_the_active_snapshot(monkeypatch):
    matcher._role_vector.cache_clear()
    monkeypatch.setattr(matcher, "_load_roles", lambda: [{"role": "Test Role", "skills": ["Alpha", "Beta"]}])

    def fake_embed(skills: list[str]) -> np.ndarray:
        vectors = {"Alpha": np.array([1.0, 0.0]), "Beta": np.array([0.0, 1.0])}
        return np.array([vectors[s] for s in skills])

    monkeypatch.setattr(embeddings, "embed", fake_embed)
    monkeypatch.setattr(weights, "weight_for", lambda role, skill: 3.0 if skill == "Alpha" else 1.0)

    vector = matcher._role_vector("Test Role")

    # An unweighted mean would be [0.5, 0.5]; weighting Alpha 3x pulls the
    # role vector toward Alpha's direction.
    assert vector[0] > vector[1]
    matcher._role_vector.cache_clear()


def test_role_vector_falls_back_to_a_plain_mean_with_no_snapshot(monkeypatch):
    # No weights_snapshot.json ships by default -- weight_for() returns
    # DEFAULT_WEIGHT (1.0) for everything, so this must equal a plain mean.
    matcher._role_vector.cache_clear()
    monkeypatch.setattr(matcher, "_load_roles", lambda: [{"role": "Test Role", "skills": ["Alpha", "Beta"]}])

    def fake_embed(skills: list[str]) -> np.ndarray:
        vectors = {"Alpha": np.array([1.0, 0.0]), "Beta": np.array([0.0, 1.0])}
        return np.array([vectors[s] for s in skills])

    monkeypatch.setattr(embeddings, "embed", fake_embed)

    vector = matcher._role_vector("Test Role")

    np.testing.assert_allclose(vector, [0.5, 0.5])
    matcher._role_vector.cache_clear()


def test_default_domain_ranks_only_engineering_roles():
    matches = match_roles(["Nursing", "Patient Care", "ACLS"], top_n=50)

    assert matches
    assert all(m.domain == "engineering" for m in matches)
    assert "Registered Nurse" not in {m.role for m in matches}


def test_healthcare_domain_ranks_general_catalogue_roles():
    matches = match_roles(["Nursing", "Patient Care", "ACLS", "BLS", "Medication Administration"],
                          top_n=3, domain="healthcare")

    assert matches[0].role == "Registered Nurse"
    assert all(m.domain == "healthcare" for m in matches)
    assert "Nursing" in matches[0].matched_skills


def test_general_domain_matching_normalizes_case_against_the_general_taxonomy():
    matches = match_roles(["nursing", "patient care"], top_n=1, domain="healthcare")

    assert set(matches[0].matched_skills) >= {"Nursing", "Patient Care"}


def test_a_security_operations_job_description_lands_on_the_cybersecurity_role():
    from app.services import jd_match

    jd = (
        "SOC Analyst. Cybersecurity fundamentals, SOC monitoring and incident response, SIEM tools such as "
        "Splunk, endpoint security, network security and TCP/IP, Linux."
    )

    result = jd_match.match_jd(["SOC", "Cybersecurity", "Network Security", "Linux", "Python"], jd)

    assert {"SOC", "Cybersecurity", "SIEM", "Splunk", "Endpoint Security"} <= set(result.jd_skills)
    assert result.closest_role.role == "Cybersecurity Analyst"
