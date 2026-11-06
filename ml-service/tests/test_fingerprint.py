"""Tests fingerprint.py's engine_fingerprint (FR-11.2). No model download
involved -- ner_model_sha/embed_model_sha hash the configured identifier
string, and taxonomy_sha hashes the real, already-present skill_taxonomy.json.
"""

from app.services.fingerprint import engine_fingerprint


def test_engine_fingerprint_has_every_required_field_populated():
    fp = engine_fingerprint()

    assert fp.engine_version
    assert fp.ner_model_sha
    assert fp.embed_model_sha
    assert fp.taxonomy_sha
    assert fp.weights_snapshot_id


def test_engine_fingerprint_hashes_are_64_character_hex_strings():
    fp = engine_fingerprint()

    for value in (fp.ner_model_sha, fp.embed_model_sha, fp.taxonomy_sha):
        assert len(value) == 64
        int(value, 16)  # raises ValueError if not valid hex


def test_engine_fingerprint_is_stable_across_calls():
    assert engine_fingerprint() == engine_fingerprint()


def test_engine_fingerprint_reports_uniform_weights_snapshot_by_default():
    # No weights_snapshot.json ships by default (Community Edition's
    # default state) -- see test_weights.py.
    assert engine_fingerprint().weights_snapshot_id == "uniform"
