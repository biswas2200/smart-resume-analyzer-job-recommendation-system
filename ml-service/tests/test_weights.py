"""Tests weights.py's snapshot loading (FR-7.5 consumer side). No snapshot
file ships in app/data/ by default (Community Edition's default state), so
these assert the "uniform weights" fallback behavior that gives -- not the
contents of any specific snapshot file, since none is bundled.
"""

from app.services import weights


def test_weight_for_defaults_to_default_weight_when_no_snapshot_is_present():
    assert not weights.WEIGHTS_SNAPSHOT_PATH.exists()

    assert weights.weight_for("Backend Software Engineer", "Java") == weights.DEFAULT_WEIGHT


def test_snapshot_id_defaults_to_uniform_when_no_snapshot_is_present():
    assert weights.snapshot_id() == "uniform"


def test_snapshot_sha256_is_deterministic_and_hex_encoded():
    first = weights.snapshot_sha256()
    second = weights.snapshot_sha256()

    assert first == second
    assert len(first) == 64
    int(first, 16)  # raises ValueError if not valid hex
