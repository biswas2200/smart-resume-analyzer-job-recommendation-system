"""The loader's handling of a local NER model directory: relative paths
resolve against ml-service/, a missing download fails loudly, and weights
that do not match the pin are refused."""

import hashlib

import pytest

from app.services.local_ner_parser import resolve_local_model_dir, verify_local_model


def test_hub_id_is_not_a_local_directory():
    assert resolve_local_model_dir("yashpwr/resume-ner-bert") is None


def test_missing_local_model_fails_with_the_fetch_hint():
    with pytest.raises(FileNotFoundError, match="fetch_ner_models.sh"):
        resolve_local_model_dir("models/ner/does-not-exist")


def test_existing_directory_resolves(tmp_path):
    assert resolve_local_model_dir(str(tmp_path)) == tmp_path


def test_weights_must_match_the_pin(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    verify_local_model(tmp_path, hashlib.sha256(b"weights").hexdigest())
    with pytest.raises(ValueError, match="NER_MODEL_REVISION"):
        verify_local_model(tmp_path, "0" * 64)
