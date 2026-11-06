"""Tests the file-upload endpoints (routers/upload.py). The document
extractor and the pipeline are faked, so no real PDF file, NER model or
LLM is involved -- the pipeline itself is covered by test_pipeline_engines.py.
"""

import io

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import ResumeProfile
from app.routers import upload
from app.services.document_extraction.base import ExtractedText

client = TestClient(app)


class _FakeExtractor:
    def __init__(self, text: str, hidden_word_count: int = 0) -> None:
        self.text = text
        self.hidden_word_count = hidden_word_count
        self.received_bytes: bytes | None = None

    def extract(self, file_bytes: bytes) -> ExtractedText:
        self.received_bytes = file_bytes
        return ExtractedText(self.text, self.hidden_word_count)


def test_parse_file_returns_profile_from_extracted_text(monkeypatch):
    fake_extractor = _FakeExtractor("Jane Doe, Python developer")
    sentinel_profile = ResumeProfile(name="Jane Doe")

    monkeypatch.setattr(upload, "get_extractor_for_filename", lambda filename: fake_extractor)
    monkeypatch.setattr(upload, "parse_resume", lambda resume_text: sentinel_profile)

    response = client.post(
        "/parse-file",
        files={"file": ("resume.pdf", io.BytesIO(b"fake pdf bytes"), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["name"] == "Jane Doe"
    assert fake_extractor.received_bytes == b"fake pdf bytes"


def test_parse_file_rejects_unsupported_extension():
    # No monkeypatching needed -- the registry itself has no heavy
    # dependencies, so this exercises the real UnsupportedDocumentTypeError
    # -> HTTP 415 mapping end to end.
    response = client.post(
        "/parse-file",
        files={"file": ("resume.odt", io.BytesIO(b"fake odt bytes"), "application/octet-stream")},
    )

    assert response.status_code == 415


def _sentinel_analysis() -> "AnalyzeResponse":
    from app.models.schemas import (
        AnalyzeResponse, AtsCheck, AtsScoreResponse, DomainDetection, EngineFingerprint,
        GapAnalysis, ResumeProfile, RoleMatch,
    )

    return AnalyzeResponse(
        profile=ResumeProfile(name="Jane Doe", skills=["Python"]),
        domain=DomainDetection(domain="engineering", name="Engineering & Technology",
                               confidence=0.9, engine="local"),
        ats_score=AtsScoreResponse(
            score=50, max_score=70, checks=[AtsCheck(name="contact_email", passed=False, detail="none")]
        ),
        matches=[RoleMatch(role="Backend Software Engineer", score=0.9, matched_skills=["Python"], missing_skills=[])],
        gaps=[GapAnalysis(role="Backend Software Engineer", missing_skills=[])],
        explanation="You're a strong match.",
        explanation_source="template",
        engine_fingerprint=EngineFingerprint(engine_version="0.3.0", ner_model_sha="a", embed_model_sha="b",
                                             taxonomy_sha="c", weights_snapshot_id="uniform"),
    )


def test_analyze_file_runs_the_pipeline_on_the_extracted_text(monkeypatch):
    fake_extractor = _FakeExtractor("Jane Doe, Python developer", hidden_word_count=7)
    calls: list[dict] = []

    def fake_analyze_text(resume_text: str, top_n: int = 3, hidden_word_count: int = 0):
        calls.append({"resume_text": resume_text, "top_n": top_n, "hidden_word_count": hidden_word_count})
        return _sentinel_analysis()

    monkeypatch.setattr(upload, "get_extractor_for_filename", lambda filename: fake_extractor)
    monkeypatch.setattr(upload.pipeline, "analyze_text", fake_analyze_text)

    response = client.post(
        "/analyze-file?top_n=2",
        files={"file": ("resume.pdf", io.BytesIO(b"fake pdf bytes"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["name"] == "Jane Doe"
    assert body["domain"]["domain"] == "engineering"
    assert body["recommendations_locked"] is False
    assert body["matches"][0]["role"] == "Backend Software Engineer"
    assert body["explanation"] == "You're a strong match."
    assert body["engine_fingerprint"]["engine_version"] == "0.3.0"
    assert fake_extractor.received_bytes == b"fake pdf bytes"
    assert calls == [{"resume_text": "Jane Doe, Python developer", "top_n": 2, "hidden_word_count": 7}]
    assert body["ai_extraction_used"] is False


def test_analyze_file_ignores_the_old_tier_parameters(monkeypatch):
    # A caller that still sends them is not rejected; they have no effect.
    seen: list[int] = []

    def fake_analyze_text(resume_text: str, top_n: int = 3, hidden_word_count: int = 0):
        seen.append(top_n)
        return _sentinel_analysis()

    monkeypatch.setattr(upload, "get_extractor_for_filename", lambda filename: _FakeExtractor("text"))
    monkeypatch.setattr(upload.pipeline, "analyze_text", fake_analyze_text)

    response = client.post(
        "/analyze-file?tier=gold&llm_allowed=true", files={"file": ("r.pdf", io.BytesIO(b"x"), "application/pdf")}
    )

    assert response.status_code == 200 and seen == [3]


def test_llm_unavailable_is_a_503(monkeypatch):
    from app.services.llm_client import LLMUnavailableError

    def unavailable(resume_text: str, top_n: int = 3, hidden_word_count: int = 0):
        raise LLMUnavailableError("GOOGLE_CLOUD_PROJECT is not set")

    monkeypatch.setattr(upload, "get_extractor_for_filename", lambda filename: _FakeExtractor("text"))
    monkeypatch.setattr(upload.pipeline, "analyze_text", unavailable)

    response = client.post(
        "/analyze-file", files={"file": ("r.pdf", io.BytesIO(b"x"), "application/pdf")}
    )

    assert response.status_code == 503
    assert "GOOGLE_CLOUD_PROJECT" in response.json()["detail"]


def test_analyze_file_rejects_unsupported_extension():
    response = client.post(
        "/analyze-file",
        files={"file": ("resume.odt", io.BytesIO(b"fake odt bytes"), "application/octet-stream")},
    )

    assert response.status_code == 415


def test_llm_usage_endpoint_reports_totals_and_pricing(monkeypatch):
    import time
    from app.config import get_settings
    from app.services import llm_client

    monkeypatch.setenv("LLM_INPUT_USD_PER_1M", "0.30")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_1M", "2.50")
    get_settings.cache_clear()
    llm_client.ledger.reset()
    llm_client.ledger.record(llm_client.LLMUsage(
        "gemini", "gemini-2.5-flash", "extract", 1500, 500, 0, 0, 0.0017, False, time.time()))
    llm_client.ledger.record(llm_client.LLMUsage(
        "gemini", "gemini-2.5-flash", "extract", 0, 0, 0, 0, 0.0, True, time.time()))

    body = client.get("/llm-usage").json()

    assert body["pricing"] == {"input_usd_per_1m": 0.30, "output_usd_per_1m": 2.50}
    assert body["totals"]["calls"] == 2 and body["totals"]["cache_hits"] == 1
    assert body["totals"]["prompt_tokens"] == 1500
    assert body["totals"]["estimated_cost_usd"] == 0.0017
    assert [d["purpose"] for d in body["totals"]["details"]] == ["extract", "extract"]

    after_reset = client.post("/llm-usage/reset").json()
    assert after_reset["totals"]["calls"] == 0
    get_settings.cache_clear()
