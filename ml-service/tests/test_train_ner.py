"""Tests the pieces of training/train_ner.py and training/label_quality.py that
decide correctness, on tiny inputs with known answers. No GPU and no training."""

import pytest

from training.data_prep.schema import LABEL_LIST
from training.label_quality import class_thresholds, resume_score, select, suspect_words
from training.train_ner import IGNORE, LABEL2ID, encode, entity_f1, merge_window_probs, spans

# --- entity F1 ----------------------------------------------------------------------


def test_spans_read_bio_like_seqeval():
    tags = ["B-Name", "I-Name", "O", "I-Skills", "B-Skills", "B-Skills", "I-Degree"]
    assert spans(tags) == {(0, 2, "Name"), (3, 4, "Skills"), (4, 5, "Skills"), (5, 6, "Skills"), (6, 7, "Degree")}


def test_entity_f1_counts_only_exact_spans():
    gold = [["B-Name", "I-Name", "O", "B-Skills"]]
    pred = [["B-Name", "O", "O", "B-Skills"]]          # name cut short: a miss and a false positive
    scores = entity_f1(gold, pred)
    assert scores["Skills"]["f1"] == 1.0
    assert scores["Name"]["f1"] == 0.0
    assert scores["overall"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5}


# --- windows ------------------------------------------------------------------------


def test_a_word_in_two_windows_gets_the_average():
    one_hot = lambda k: [1.0 if i == k else 0.0 for i in range(3)]
    windows = [([None, 0, 1, 1], [None, one_hot(1), one_hot(2), one_hot(0)]),   # word 1 = subwords 2,3
               ([None, 1, 2], [None, one_hot(0), one_hot(1)])]
    merged = merge_window_probs(3, windows)
    assert merged[0] == one_hot(1)
    assert merged[1] == [0.5, 0.0, 0.5]                # first subword of word 1 in each window
    assert merged[2] == one_hot(1)


def _tokenizer():
    transformers = pytest.importorskip("transformers")
    from training.config import ner_config
    try:
        return transformers.AutoTokenizer.from_pretrained(
            ner_config.base_model, revision=ner_config.base_model_revision, local_files_only=True)
    except OSError:
        pytest.skip("teacher tokenizer not cached on this machine")


def test_only_first_subwords_carry_labels():
    row = {"id": "x", "tokens": ["Abhishek", "Jha", "Python"], "ner_tags": ["B-Name", "I-Name", "B-Skills"]}
    window = encode(row, _tokenizer())[0]
    labelled = [LABEL_LIST[label] for label in window["labels"] if label != IGNORE]
    assert labelled == ["B-Name", "I-Name", "B-Skills"]
    assert window["labels"][0] == IGNORE and window["labels"][-1] == IGNORE    # [CLS], [SEP]


def test_long_resumes_become_overlapping_windows_covering_every_word():
    row = {"id": "x", "tokens": [f"word{i}" for i in range(400)], "ner_tags": ["O"] * 400}
    windows = encode(row, _tokenizer(), max_length=128, stride=32)
    assert len(windows) > 1 and all(len(w["input_ids"]) <= 128 for w in windows)
    assert set().union(*({i for i in w["word_ids"] if i is not None} for w in windows)) == set(range(400))


# --- distillation loss ----------------------------------------------------------------


def test_distillation_loss_is_zero_kd_when_student_matches_teacher():
    torch = pytest.importorskip("torch")
    from training.train_ner import kd_loss

    logits = torch.tensor([[[2.0, 0.0, -1.0], [0.0, 3.0, 0.0]]])
    labels = torch.tensor([[0, IGNORE]])
    only_kd = kd_loss(logits, logits.clone(), labels, temperature=2.0, alpha_ce=0.0, alpha_kd=1.0)
    assert only_kd.item() == pytest.approx(0.0, abs=1e-6)
    worse = kd_loss(logits, -logits, labels, temperature=2.0, alpha_ce=0.0, alpha_kd=1.0)
    assert worse.item() > 0.1


# --- label quality -----------------------------------------------------------------------


def _probs(confident_in: str, p: float = 0.9) -> list[float]:
    rest = (1 - p) / (len(LABEL_LIST) - 1)
    return [p if label == confident_in else rest for label in LABEL_LIST]


def test_a_missed_entity_and_a_wrong_label_are_suspect_and_agreement_is_not():
    # Thresholds need correctly labelled examples of each class, as real data has.
    rows = [{"id": "a", "tokens": ["Ann", "Python", "Leeds"], "ner_tags": ["B-Name", "O", "B-Name"]},
            {"id": "b", "tokens": ["Bob", "Java", "Oxford", "at", "in"],
             "ner_tags": ["B-Name", "B-Skills", "B-College Name", "O", "O"]}]
    probs = {"a": [_probs("B-Name"), _probs("B-Skills"), _probs("B-College Name")],
             "b": [_probs("B-Name"), _probs("B-Skills"), _probs("B-College Name"), _probs("O"), _probs("O")]}
    thresholds = class_thresholds(rows, probs)
    found = suspect_words(rows[0], probs["a"], thresholds)
    assert [(i, given, suggested) for i, given, suggested, _ in found] == [
        (1, "O", "B-Skills"), (2, "B-Name", "B-College Name")]
    assert suspect_words(rows[1], probs["b"], thresholds) == []
    assert resume_score(rows[0], probs["a"], found) == pytest.approx(2 / 3)


def test_selection_respects_both_caps_and_the_minimum_score():
    scores = {f"r{i}": i / 100 for i in range(100)}            # r99 is the worst
    assert select(scores, set(), 100, max_remove=0.05, max_total=0.15, min_score=0.2) == [
        "r99", "r98", "r97", "r96", "r95"]
    already = {f"r{i}" for i in range(90, 100)}                 # 10 removed in earlier rounds
    assert select(scores, already, 100, 0.05, 0.15, 0.2) == ["r89", "r88", "r87", "r86", "r85"]
    assert select(scores, already | {"r85", "r86", "r87", "r88", "r89"}, 100, 0.05, 0.15, 0.2) == []
    assert select(scores, set(), 100, 0.05, 0.15, min_score=0.98) == ["r99", "r98"]
