"""Checks the NER training configuration against the models it names: the
app must serve a pinned model trained from the training base, and the student must split text
into exactly the teacher's tokens, or token-by-token distillation compares
mismatched positions."""

import pytest

from app.config import Settings
from training.config import ner_config


def test_app_serves_a_pinned_model_trained_from_the_training_base():
    # Code defaults, not .env. Training starts from the upstream model (the
    # 60 % / 64 % baselines); the app serves run 1's fine-tuned teacher,
    # pinned by the SHA-256 of its weights.
    fields = Settings.model_fields
    assert ner_config.base_model == "yashpwr/resume-ner-bert"
    assert fields["ner_model_name"].default == "models/ner/teacher-run1"
    assert len(fields["ner_model_revision"].default) == 64


def _cached_tokenizer(repo: str, revision: str):
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained(repo, revision=revision, local_files_only=True)
    except OSError:
        pytest.skip(f"{repo} tokenizer not cached on this machine")


def test_student_splits_resume_text_exactly_like_the_teacher():
    teacher = _cached_tokenizer(ner_config.base_model, ner_config.base_model_revision)
    student = _cached_tokenizer(ner_config.student_model, ner_config.student_model_revision)
    text = "Abhishek Jha\nB.Tech - Computer Science, IIT Delhi (2016)\nSAP ABAP | McKinsey & Company | São Paulo"
    assert student.tokenize(text) == teacher.tokenize(text)
    assert student.get_vocab() == teacher.get_vocab()
