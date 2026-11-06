"""Loads the weights snapshot the backend's admin export endpoint publishes
(SRS FR-7.5: {snapshot_id, created_at, sha256, weights: {role: {skill:
weight}}}), so matcher.py can compute each role's *weighted* skill vector
(FR-3.2) instead of a plain mean -- see docs/editions-and-parity.md §2 and
docs/lld.md §7.4.

A missing file or a missing (role, skill) entry both fall back to weight
1.0, matching the backend's SkillVectorService.DEFAULT_WEIGHT -- so a role or
skill with no EMA history yet still counts in the match, just without any
learned emphasis, and the engine runs identically with or without a snapshot
ever having been placed in app/data/ (the Community Edition default).
"""

import hashlib
import json
from functools import lru_cache

from app.config import DATA_DIR

WEIGHTS_SNAPSHOT_PATH = DATA_DIR / "weights_snapshot.json"
DEFAULT_WEIGHT = 1.0
_UNSNAPSHOTTED_ID = "uniform"


@lru_cache
def _load_snapshot() -> dict:
    if not WEIGHTS_SNAPSHOT_PATH.exists():
        return {"snapshot_id": _UNSNAPSHOTTED_ID, "weights": {}}
    with open(WEIGHTS_SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def snapshot_id() -> str:
    """The active snapshot's id, or "uniform" when none has been shipped --
    the value engine_fingerprint.weights_snapshot_id reports either way.
    """
    return _load_snapshot().get("snapshot_id", _UNSNAPSHOTTED_ID)


def snapshot_sha256() -> str:
    """A content hash of whatever snapshot file is actually present (or of
    the fixed "no snapshot" marker when there isn't one), for fingerprint.py.
    """
    if not WEIGHTS_SNAPSHOT_PATH.exists():
        return hashlib.sha256(_UNSNAPSHOTTED_ID.encode("utf-8")).hexdigest()
    return hashlib.sha256(WEIGHTS_SNAPSHOT_PATH.read_bytes()).hexdigest()


def weight_for(role: str, skill: str) -> float:
    """This role/skill pair's snapshot weight, or DEFAULT_WEIGHT if there's
    no snapshot, or no entry for this role, or no entry for this skill.
    """
    weights = _load_snapshot().get("weights", {})
    return weights.get(role, {}).get(skill, DEFAULT_WEIGHT)


def install_snapshot(snapshot: dict) -> None:
    """Writes a snapshot pushed by the backend as weights_snapshot.json and
    drops every cache built from the previous one, so the next match uses it.
    On a stateless host (Cloud Run) the file lasts until the instance
    restarts; the backend pushes again after every daily market update.
    """
    from app.services import fingerprint, matcher  # imported here: both import this module

    WEIGHTS_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = WEIGHTS_SNAPSHOT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    tmp.replace(WEIGHTS_SNAPSHOT_PATH)
    _load_snapshot.cache_clear()
    matcher._role_vector.cache_clear()
    fingerprint.engine_fingerprint.cache_clear()

