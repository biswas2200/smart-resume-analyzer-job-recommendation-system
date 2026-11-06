"""Tests training/data_prep/training_set.py with small hand-built records whose
correct output is known in advance."""

import json
from collections import Counter

import pytest

from training.data_prep.schema import Entity, Record, validate_record
from training.data_prep.training_set import (
    build, drop_non_year_graduation_years, fill_placeholders, in_pool_dev, merge_skills,
)

TEXT = "Ann Lee\nSkills: Python, SQL and Excel\nB.Sc, Leeds University, 2015"


def _span(text: str, value: str, label: str) -> Entity:
    start = text.index(value)
    return Entity(start, start + len(value), label)


def _labels(record: Record) -> list[tuple[str, str]]:
    return [(e.label, record.text[e.start:e.end]) for e in record.entities]


def test_skills_come_from_gemini_and_every_other_field_from_the_human_labels():
    human = Record("dataturks-0001", "dataturks", "train", TEXT, [
        _span(TEXT, "Ann Lee", "Name"),
        _span(TEXT, "Python, SQL and Excel", "Skills"),
        _span(TEXT, "Leeds University", "College Name"),
    ])
    gemini = Record("dataturks-0001", "gemini:x", "train", TEXT, [
        _span(TEXT, "Ann Lee", "Designation"),          # wrong, but not a skill: ignored
        _span(TEXT, "Python", "Skills"), _span(TEXT, "SQL", "Skills"), _span(TEXT, "Excel", "Skills"),
    ])
    stats = Counter()
    merged = merge_skills(human, gemini, stats)
    assert _labels(merged) == [("Name", "Ann Lee"), ("Skills", "Python"), ("Skills", "SQL"),
                               ("Skills", "Excel"), ("College Name", "Leeds University")]
    assert stats == {"human_skill_spans_replaced": 1, "gemini_skill_spans_added": 3}


def test_a_gemini_skill_overlapping_a_human_label_is_dropped():
    human = Record("dataturks-0002", "dataturks", "train", TEXT, [_span(TEXT, "Leeds University", "College Name")])
    gemini = Record("dataturks-0002", "gemini:x", "train", TEXT, [_span(TEXT, "Leeds", "Skills")])
    stats = Counter()
    assert _labels(merge_skills(human, gemini, stats)) == [("College Name", "Leeds University")]
    assert stats["gemini_skill_overlapping_human_label_dropped"] == 1


def test_different_texts_cannot_be_merged():
    human = Record("dataturks-0003", "dataturks", "train", TEXT)
    with pytest.raises(ValueError):
        merge_skills(human, Record("dataturks-0003", "gemini:x", "train", TEXT + " "), Counter())


def test_graduation_years_without_a_year_are_dropped():
    text = "B.A. 2014 to Present, May"
    record = Record("livecareer-1", "gemini:x", "train", text, [
        _span(text, "2014", "Graduation Year"), _span(text, "Present", "Graduation Year"),
        _span(text, "May", "Graduation Year"),
    ])
    stats = Counter()
    assert _labels(drop_non_year_graduation_years(record, stats)) == [("Graduation Year", "2014")]
    assert stats["graduation_year_without_year_dropped"] == 2


def test_pool_dev_is_a_stable_five_percent():
    ids = [f"livecareer-{n}" for n in range(20000)]
    chosen = [i for i in ids if in_pool_dev(i)]
    assert 0.04 < len(chosen) / len(ids) < 0.06
    assert chosen == [i for i in ids if in_pool_dev(i)]


def _write(path, records):
    path.write_text("".join(json.dumps(r.to_dict()) + "\n" for r in records), encoding="utf-8")


def _fixture(tmp_path, with_skills=True):
    turks = [
        Record("dataturks-0001", "dataturks", "train", TEXT, [_span(TEXT, "Python, SQL and Excel", "Skills")]),
        Record("dataturks-0111", "dataturks", "test", TEXT, [_span(TEXT, "Python, SQL and Excel", "Skills")]),
    ]
    skills = [Record("dataturks-0001", "gemini:x", "train", TEXT, [_span(TEXT, "SQL", "Skills")])] if with_skills else []
    pool = [Record("livecareer-7", "gemini:x", "train", TEXT, [_span(TEXT, "B.Sc", "Degree")])]
    for name, records in (("turks", turks), ("skills", skills), ("pool", pool)):
        _write(tmp_path / f"{name}.jsonl", records)
    return tmp_path / "turks.jsonl", tmp_path / "pool.jsonl", tmp_path / "skills.jsonl", tmp_path / "out"


def test_build_keeps_test_untouched_and_writes_every_split(tmp_path):
    turks, pool, skills, out = _fixture(tmp_path)
    report = build(turks, pool, skills, out)
    test = [json.loads(line) for line in open(out / "records/test.jsonl")]
    assert [e["end"] - e["start"] for e in test[0]["entities"]] == [len("Python, SQL and Excel")]
    train_ids = {json.loads(line)["id"] for line in open(out / "records/train.jsonl")}
    dev_ids = {json.loads(line)["id"] for line in open(out / "records/dev.jsonl")}
    assert "dataturks-0001" in train_ids and "dataturks-0111" not in train_ids | dev_ids
    assert "livecareer-7" in train_ids | dev_ids
    for split in ("train", "dev", "test"):
        assert (out / "bio" / f"{split}.jsonl").exists()
    assert report["cleaning"]["gemini_skill_spans_added"] == 1


def test_build_refuses_when_a_train_resume_has_no_gemini_skills(tmp_path):
    turks, pool, skills, out = _fixture(tmp_path, with_skills=False)
    with pytest.raises(ValueError, match="no Gemini skills"):
        build(turks, pool, skills, out)
    assert not out.exists()


# --- placeholder filling ---------------------------------------------------------------


def test_placeholders_are_filled_labelled_and_later_entities_shift():
    text = "HR Director\nCompany Name － City , State\nPython, SQL"
    record = Record("livecareer-9", "gemini:x", "train", text,
                    [_span(text, "HR Director", "Designation"), _span(text, "Python", "Skills"), _span(text, "SQL", "Skills")])
    stats = Counter()

    filled = fill_placeholders(record, stats)

    labels = _labels(filled)
    assert labels[0] == ("Designation", "HR Director")
    assert labels[1][0] == "Companies worked at" and labels[1][1] not in ("Company Name", "")
    assert labels[2][0] == "Location" and " , " in labels[2][1] and labels[2][1] != "City , State"
    assert labels[3:] == [("Skills", "Python"), ("Skills", "SQL")]       # still on the right words
    assert "Company Name" not in filled.text and "City , State" not in filled.text
    assert validate_record(filled) == []
    assert stats == {"placeholder_filled_Companies worked at": 1, "placeholder_filled_Location": 1}


def test_filling_depends_only_on_the_resume_id():
    text = "Company Name City , State"
    a = fill_placeholders(Record("livecareer-1", "g", "train", text), Counter())
    b = fill_placeholders(Record("livecareer-1", "g", "train", text), Counter())
    assert a.text == b.text


def test_a_company_placeholder_on_an_education_line_is_left_alone():
    text = "Bachelor of Science Company Name City , State"
    stats = Counter()
    filled = fill_placeholders(Record("livecareer-2", "g", "train", text), stats)
    assert "Company Name" in filled.text
    assert [label for label, _ in _labels(filled)] == ["Location"]
    assert stats["placeholder_on_education_line_kept"] == 1


def test_a_placeholder_inside_an_existing_entity_is_left_alone():
    text = "Manager at Company Name"
    record = Record("livecareer-3", "g", "train", text, [Entity(0, len(text), "Designation")])
    stats = Counter()
    assert fill_placeholders(record, stats).text == text
    assert stats["placeholder_inside_entity_kept"] == 1
