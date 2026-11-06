"""Fetching the NER model from the bucket at start-up: the folder is copied
only when missing, checked against the pin before it takes the model's
place, and a bad download leaves nothing behind. A fake bucket stands in for
Cloud Storage, so these tests never reach GCP."""

import hashlib
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from app.services import gcs_download
from app.services.gcs_download import download_folder, parse_gcs_uri
from app.services.local_ner_parser import ensure_local_model

WEIGHTS = b"weights"


class FakeResponse:
    def __init__(self, body=None, content=b""):
        self._body = body
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._body

    def iter_content(self, chunk_size):
        yield self._content


class FakeBucket:
    """Answers the two JSON API calls download_folder makes: list a prefix
    (two pages, to cover paging) and fetch one object's bytes."""

    def __init__(self, objects):
        self.objects = objects
        self.calls = 0

    def get(self, url, params=None, stream=False):
        self.calls += 1
        if params.get("alt") == "media":
            return FakeResponse(content=self.objects[unquote(url.rsplit("/o/", 1)[1])])
        names = sorted(name for name in self.objects if name.startswith(params["prefix"]))
        if "pageToken" in params:
            return FakeResponse({"items": [{"name": name} for name in names[1:]]})
        if len(names) < 2:
            return FakeResponse({"items": [{"name": name} for name in names]})
        return FakeResponse({"items": [{"name": names[0]}], "nextPageToken": "2"})


def model_objects(weights=WEIGHTS):
    return {
        "runs/teacher/model.safetensors": weights,
        "runs/teacher/config.json": b"{}",
        "runs/teacher/": b"",
        "runs/teacher/checkpoints/old.bin": b"skip me",
        "runs/student/model.safetensors": b"other model",
    }


def settings_for(tmp_path, **overrides):
    values = {
        "parser_backend": "local",
        "ner_model_gcs_uri": "gs://bucket/runs/teacher",
        "ner_model_name": str(tmp_path / "teacher-run1"),
        "ner_model_revision": hashlib.sha256(WEIGHTS).hexdigest(),
    }
    return SimpleNamespace(**(values | overrides))


def test_parse_gcs_uri():
    assert parse_gcs_uri("gs://bucket/runs/teacher") == ("bucket", "runs/teacher/")
    assert parse_gcs_uri("gs://bucket/runs/teacher/") == ("bucket", "runs/teacher/")
    assert parse_gcs_uri("gs://bucket") == ("bucket", "")
    with pytest.raises(ValueError):
        parse_gcs_uri("/srv/models/teacher")


def test_download_folder_copies_only_the_folders_own_files(tmp_path):
    count = download_folder("gs://bucket/runs/teacher", tmp_path / "out", session=FakeBucket(model_objects()))
    assert count == 2
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == ["config.json", "model.safetensors"]
    assert (tmp_path / "out" / "model.safetensors").read_bytes() == WEIGHTS


def test_download_folder_refuses_an_empty_prefix(tmp_path):
    with pytest.raises(FileNotFoundError, match="gs://bucket/runs/missing"):
        download_folder("gs://bucket/runs/missing", tmp_path / "out", session=FakeBucket({"runs/x/a": b""}))


def test_missing_model_is_downloaded_and_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(gcs_download, "_adc_session", lambda: FakeBucket(model_objects()))
    ensure_local_model(settings_for(tmp_path))
    assert (tmp_path / "teacher-run1" / "model.safetensors").read_bytes() == WEIGHTS
    assert not (tmp_path / ".teacher-run1.download").exists()


def test_download_with_the_wrong_weights_leaves_nothing_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(gcs_download, "_adc_session", lambda: FakeBucket(model_objects(b"tampered")))
    with pytest.raises(ValueError, match="NER_MODEL_REVISION"):
        ensure_local_model(settings_for(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"ner_model_gcs_uri": ""},
        {"parser_backend": "llm"},
        {"ner_model_name": "yashpwr/resume-ner-bert"},
    ],
)
def test_nothing_is_downloaded_when_not_needed(tmp_path, monkeypatch, overrides):
    bucket = FakeBucket(model_objects())
    monkeypatch.setattr(gcs_download, "_adc_session", lambda: bucket)
    ensure_local_model(settings_for(tmp_path, **overrides))
    assert bucket.calls == 0


def test_an_existing_folder_is_left_alone(tmp_path, monkeypatch):
    (tmp_path / "teacher-run1").mkdir()
    bucket = FakeBucket(model_objects())
    monkeypatch.setattr(gcs_download, "_adc_session", lambda: bucket)
    ensure_local_model(settings_for(tmp_path))
    assert bucket.calls == 0
