"""Computes the engine_fingerprint every analysis response and GET /health
include (SRS FR-11.2): {engine_version, ner_model_sha, embed_model_sha,
taxonomy_sha, weights_snapshot_id} -- the tuple that lets a Community user
prove, without trusting anyone's word for it, that they're running the same
core engine as a given web deployment (see docs/editions-and-parity.md).

taxonomy_sha is a real content hash of every bundled data file that shapes a
result -- both skill taxonomies, both role catalogues and domains.json -- so
it changes automatically whenever any of them is edited. ner_model_sha and
embed_model_sha are hashes of the *configured model identifier* (name +
pinned revision), not of the downloaded model weights themselves -- real
content-hash pinning of the weights is a further step (ONNX export baked
into the release image, see docs/editions-and-parity.md's implementation
order) that this fingerprint mechanism doesn't depend on to exist. Until
then, these hashes still change whenever the configured model or its pinned
revision changes, which is what actually matters for detecting a mismatch.
"""

import hashlib
from functools import lru_cache

from app.config import DATA_DIR, get_settings
from app.models.schemas import EngineFingerprint
from app.services.weights import snapshot_id

# Order is fixed so the combined hash is stable; a file that is absent (a
# stripped-down build) hashes as empty rather than failing.
DATA_FILES = (
    DATA_DIR / "skill_taxonomy.json",
    DATA_DIR / "skill_taxonomy_general.json",
    DATA_DIR / "role_skills.json",
    DATA_DIR / "role_skills_general.json",
    DATA_DIR / "domains.json",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_files(paths) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()


@lru_cache
def engine_fingerprint() -> EngineFingerprint:
    settings = get_settings()
    return EngineFingerprint(
        engine_version=settings.engine_version,
        ner_model_sha=_sha256_text(f"{settings.ner_model_name}@{settings.ner_model_revision}"),
        embed_model_sha=_sha256_text(f"{settings.embedding_model}@{settings.embedding_model_revision}"),
        taxonomy_sha=_sha256_files(DATA_FILES),
        weights_snapshot_id=snapshot_id(),
    )
