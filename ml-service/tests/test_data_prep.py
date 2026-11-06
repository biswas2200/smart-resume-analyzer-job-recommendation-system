"""Tests training/data_prep with small hand-built inputs whose correct output
is known in advance, so every cleaning rule is checked on its own."""

import json
from collections import Counter
from pathlib import Path

import pytest

from training.data_prep import dataturks, livecareer
from training.data_prep.bio import to_bio
from training.data_prep.build import build
from training.data_prep.schema import LABEL_LIST, Entity, Record, validate_record


def _turks(content: str, *annotations: tuple[str, int, int, str]) -> dict:
    """A DataTurks object; each annotation is (label, start, inclusive end, text)."""
    return {
        "content": content,
        "annotation": [
            {"label": [label], "points": [{"start": s, "end": e, "text": t}]} for label, s, e, t in annotations
        ],
        "extras": None,
    }


# --- schema -------------------------------------------------------------------


def test_label_list_has_the_models_25_labels_in_order():
    assert len(LABEL_LIST) == 25
    assert LABEL_LIST[:3] == ["O", "B-College Name", "I-College Name"]
    assert LABEL_LIST[-2:] == ["B-Years of Experience", "I-Years of Experience"]


def test_label_list_matches_the_cached_model_config():
    snapshots = Path.home() / ".cache/huggingface/hub/models--yashpwr--resume-ner-bert/snapshots"
    configs = sorted(snapshots.glob("*/config.json")) if snapshots.exists() else []
    if not configs:
        pytest.skip("NER model not cached on this machine")
    id2label = json.loads(configs[0].read_text())["id2label"]
    assert [id2label[str(i)] for i in range(len(id2label))] == LABEL_LIST


def test_validate_record_flags_each_kind_of_problem():
    record = Record(
        id="r1",
        source="t",
        split="train",
        text="Jane Doe  Acme",
        entities=[
            Entity(0, 4, "Name"),
            Entity(2, 8, "Name"),  # overlaps the first
            Entity(8, 14, "Companies worked at"),  # starts with a space
            Entity(10, 99, "Skills"),  # past the end
            Entity(0, 1, "Hobby"),  # unknown label
        ],
    )
    problems = " | ".join(validate_record(record))
    assert "overlaps" in problems
    assert "whitespace" in problems
    assert "outside the text" in problems
    assert "unknown label" in problems


def test_valid_record_has_no_problems():
    record = Record("r1", "t", "train", "Jane Doe", [Entity(0, 8, "Name")])
    assert validate_record(record) == []


# --- DataTurks ----------------------------------------------------------------


def test_inclusive_end_becomes_exclusive():
    stats = Counter()
    record = dataturks.convert(_turks("Jane Doe\nAcme", ("Name", 0, 7, "Jane Doe")), 1, stats)
    assert [(e.start, e.end) for e in record.entities] == [(0, 8)]
    assert record.text[0:8] == "Jane Doe"


def test_wrong_offset_is_repaired_to_the_nearest_occurrence():
    content = "Infosys intro\n\nWorked at Infosys as engineer"
    stats = Counter()
    # Stated at 30, but "Infosys" is at 0 and 25: 25 is nearer.
    record = dataturks.convert(_turks(content, ("Companies worked at", 30, 36, "Infosys")), 1, stats)
    assert [(e.start, e.end) for e in record.entities] == [(25, 32)]
    assert stats["offset_repaired"] == 1


def test_annotation_text_missing_from_the_resume_is_dropped():
    stats = Counter()
    record = dataturks.convert(_turks("Jane Doe", ("Name", 0, 3, "John Smith")), 1, stats)
    assert record.entities == []
    assert stats["not_found"] == 1


def test_whitespace_at_span_edges_is_trimmed():
    stats = Counter()
    content = "Skills\n\nPython, SQL\n\n"
    record = dataturks.convert(_turks(content, ("Skills", 6, 20, "\n\nPython, SQL\n\n")), 1, stats)
    (entity,) = record.entities
    assert content[entity.start:entity.end] == "Python, SQL"
    assert stats["whitespace_trimmed"] == 1


def test_overlapping_spans_keep_the_longer_one():
    content = "oracle India Limited"
    stats = Counter()
    record = dataturks.convert(
        _turks(content, ("Companies worked at", 0, 5, "oracle"), ("Companies worked at", 0, 19, content)), 1, stats
    )
    assert [(e.start, e.end) for e in record.entities] == [(0, 20)]
    assert stats["overlap_dropped"] == 1


def test_unknown_and_missing_labels_are_dropped():
    stats = Counter()
    raw = _turks("Jane Doe x", ("UNKNOWN", 9, 9, "x"))
    raw["annotation"].append({"label": [], "points": [{"start": 0, "end": 3, "text": "Jane"}]})
    record = dataturks.convert(raw, 1, stats)
    assert record.entities == []
    assert stats["label_dropped"] == 1
    assert stats["no_label_dropped"] == 1


@pytest.mark.parametrize("position, split", [(1, "train"), (100, "train"), (101, "dev"), (110, "dev"), (111, "test"), (220, "test")])
def test_split_follows_the_baseline_file_order(position, split):
    assert dataturks.split_for(position) == split


# --- LiveCareer ---------------------------------------------------------------


def test_html_to_text_keeps_one_block_per_line():
    html = '<div class="x"><div>Experience</div><p>Line   Cook ,  2012</p><br/><div></div></div>'
    assert livecareer.html_to_text(html) == "Experience\nLine Cook , 2012"


def _write_csv(path: Path, rows: list[tuple[str, str, str]]) -> None:
    import csv

    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID", "Resume_str", "Resume_html", "Category"])
        for row_id, html, category in rows:
            writer.writerow([row_id, "", html, category])


def test_livecareer_excludes_unseen_test_ids_duplicates_and_short_texts(tmp_path):
    long_html = "<div>" + "Experience line. " * 30 + "</div>"
    _write_csv(
        tmp_path / "Resume.csv",
        [
            ("1", long_html, "HR"),
            ("2", long_html, "HR"),  # duplicate text of 1
            ("3", "<div>too short</div>", "CHEF"),
            ("4", long_html.replace("Experience", "Education"), "CHEF"),  # in the unseen test set
            ("5", long_html.replace("Experience", "Skills"), "SALES"),
        ],
    )
    records, stats = livecareer.load(tmp_path / "Resume.csv", excluded_ids={"4"})
    assert [r.id for r in records] == ["livecareer-1", "livecareer-5"]
    assert all(r.split == "unlabelled" and r.entities == [] for r in records)
    assert (stats["duplicate"], stats["too_short"], stats["excluded_unseen_test"]) == (1, 1, 1)


# --- BIO ----------------------------------------------------------------------


def test_bio_marks_first_word_b_and_the_rest_i():
    text = "Priya Sharma\nSoftware Engineer at Infosys"
    record = Record("r", "t", "train", text, [Entity(0, 12, "Name"), Entity(13, 30, "Designation"), Entity(34, 41, "Companies worked at")])
    bio = to_bio(record)
    assert bio["tokens"] == ["Priya", "Sharma", "Software", "Engineer", "at", "Infosys"]
    assert bio["ner_tags"] == ["B-Name", "I-Name", "B-Designation", "I-Designation", "O", "B-Companies worked at"]


def test_bio_keeps_technical_words_whole_and_splits_punctuation():
    text = "B.Tech, C++ and C# (e-mail)"
    bio = to_bio(Record("r", "t", "train", text, [Entity(0, 6, "Degree"), Entity(8, 11, "Skills")]))
    assert bio["tokens"] == ["B.Tech", ",", "C++", "and", "C#", "(", "e-mail", ")"]
    assert bio["ner_tags"][:3] == ["B-Degree", "O", "B-Skills"]


def test_bio_two_adjacent_entities_of_the_same_type_both_start_with_b():
    text = "Python Java"
    bio = to_bio(Record("r", "t", "train", text, [Entity(0, 6, "Skills"), Entity(7, 11, "Skills")]))
    assert bio["ner_tags"] == ["B-Skills", "B-Skills"]


# --- build (end to end on tiny files) -----------------------------------------


def test_build_writes_every_file_and_a_consistent_report(tmp_path):
    datasets = tmp_path / "datasets"
    (datasets / "archive (1)").mkdir(parents=True)
    (datasets / "archive" / "Resume").mkdir(parents=True)
    turks_lines = [
        json.dumps(_turks(f"Person {i}\nEngineer", ("Name", 0, 7, f"Person {i}"))) for i in range(1, 113)
    ]
    (datasets / dataturks_path()).write_text("\n".join(turks_lines) + "\n", encoding="utf-8")
    _write_csv(datasets / "archive" / "Resume" / "Resume.csv", [("9", "<div>" + "Summary text. " * 40 + "</div>", "HR")])

    report = build(datasets, tmp_path / "out")

    assert report["resumes_per_split"] == {"train": 100, "dev": 10, "test": 2, "unlabelled": 1}
    assert report["entities_per_label"] == {"Name": 112}
    for name in ["records/dataturks.jsonl", "records/livecareer_unlabelled.jsonl", "bio/train.jsonl", "bio/dev.jsonl", "bio/test.jsonl", "report.json"]:
        assert (tmp_path / "out" / name).exists(), name
    first = json.loads((tmp_path / "out" / "bio" / "train.jsonl").read_text().splitlines()[0])
    assert first["ner_tags"][:3] == ["B-Name", "I-Name", "O"]


def test_build_writes_nothing_when_a_record_is_invalid(tmp_path, monkeypatch):
    datasets = tmp_path / "datasets"
    (datasets / "archive (1)").mkdir(parents=True)
    (datasets / "archive" / "Resume").mkdir(parents=True)
    (datasets / dataturks_path()).write_text(json.dumps(_turks("Jane Doe", ("Name", 0, 7, "Jane Doe"))) + "\n")
    _write_csv(datasets / "archive" / "Resume" / "Resume.csv", [])
    monkeypatch.setattr("training.data_prep.build.validate_record", lambda record: ["broken on purpose"])

    with pytest.raises(ValueError, match="broken on purpose"):
        build(datasets, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def dataturks_path() -> Path:
    from training.data_prep.build import DATATURKS_PATH

    return DATATURKS_PATH


# --- Gemini answer alignment (no API call) ------------------------------------


def test_gemini_answers_are_located_in_order_and_bad_ones_counted():
    from training.data_prep.gemini_label import align

    text = "Line Cook\nCompany Name - City , State\nLine Cook again at Hilton"
    stats = Counter()
    entities = align(
        text,
        [
            {"label": "Designation", "text": "Line Cook"},
            {"label": "Companies worked at", "text": "Company Name"},  # placeholder
            {"label": "Location", "text": "City"},  # placeholder
            {"label": "Designation", "text": "Line Cook"},  # second occurrence, found after the first
            {"label": "Companies worked at", "text": "Hilton Hotels"},  # not in the text: invented
            {"label": "Hobby", "text": "Hilton"},  # unknown label
        ],
        stats,
    )
    assert [(text[e.start:e.end], e.start) for e in entities] == [("Line Cook", 0), ("Line Cook", 38)]
    assert (stats["placeholder_dropped"], stats["not_in_text"], stats["bad_label_or_empty"]) == (2, 1, 1)


def test_gemini_response_schema_only_allows_the_requested_labels():
    from training.data_prep.gemini_label import LABELS, RESPONSE_SCHEMA

    enum = RESPONSE_SCHEMA["properties"]["entities"]["items"]["properties"]["label"]["enum"]
    assert enum == list(LABELS)
    assert "UNKNOWN" not in enum


# --- Graduation-year rules ------------------------------------------------------


def _years(text, entities):
    return [text[e.start:e.end] for e in entities if e.label == "Graduation Year"]


def test_graduation_year_inside_a_job_date_range_is_dropped():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "HR Assistant 04/2014 to 02/2016\nMay 2014 to September 2015 Company"
    entities = [Entity(13, 20, "Graduation Year"), Entity(24, 31, "Graduation Year"), Entity(32, 40, "Graduation Year")]
    stats = Counter()
    assert _years(text, fix_graduation_years(text, entities, stats)) == []
    assert stats["graduation_year_dropped"] == 3


def test_graduation_year_on_a_certification_line_is_dropped():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "Expect to complete aPHR certification in 2017"
    stats = Counter()
    assert fix_graduation_years(text, [Entity(41, 45, "Graduation Year")], stats) == []


def test_year_on_the_line_above_a_school_is_added():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "Education\n2008\nZambia Accountancy College - ACCA\n2001\nDiploma : Accountancy"
    school = text.index("Zambia Accountancy College")
    degree = text.index("Diploma : Accountancy")
    entities = [Entity(school, school + 26, "College Name"), Entity(degree, degree + 21, "Degree")]
    stats = Counter()
    assert _years(text, fix_graduation_years(text, entities, stats)) == ["2008", "2001"]


def test_year_next_to_a_degree_is_added_but_a_job_range_beside_it_is_not():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "High School Diploma : Jun 2015 Oldham County High School\nBookseller , 08/2016 to Current"
    degree = Entity(0, 19, "Degree")
    years = _years(text, fix_graduation_years(text, [degree], Counter()))
    assert years == ["Jun 2015"]


def test_education_date_range_gives_its_end_year():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "Bachelor of Engineering\nAnna University\n2016 to 2018"
    school = text.index("Anna University")
    model_says = [Entity(school, school + 15, "College Name"), Entity(text.index("2016"), text.index("2016") + 4, "Graduation Year")]
    assert _years(text, fix_graduation_years(text, model_says, Counter())) == ["2018"]


def test_year_in_prose_away_from_education_is_dropped():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "I joined Accenture in 2006 and moved to the USA.\n\nEducation\nB.E, Anna University"
    entities = [Entity(text.index("2006"), text.index("2006") + 4, "Graduation Year"),
                Entity(text.index("Anna University"), text.index("Anna University") + 15, "College Name")]
    stats = Counter()
    assert _years(text, fix_graduation_years(text, entities, stats)) == []
    assert stats["graduation_year_dropped"] == 1


def test_overlapping_year_spans_keep_the_longer_one():
    from training.data_prep.gemini_label import fix_graduation_years
    from training.data_prep.schema import validate_record

    text = "MBA, Pune University, May 2006"
    entities = [Entity(5, 20, "College Name"), Entity(26, 30, "Graduation Year")]  # model labelled only "2006"
    result = fix_graduation_years(text, entities, Counter())
    assert _years(text, result) == ["May 2006"]
    assert validate_record(Record("r", "t", "test", text, result)) == []


def test_year_after_a_blank_line_below_the_school_is_found():
    from training.data_prep.gemini_label import fix_graduation_years

    text = "EDUCATION\n\nMBA in marketing-tourism\n\nCalicut University -  Calicut, Kerala\n\n2016 to 2018\n\nhttps://www.indeed.com/r/x"
    school = text.index("Calicut University")
    assert _years(text, fix_graduation_years(text, [Entity(school, school + 18, "College Name")], Counter())) == ["2018"]


def test_not_applicable_values_are_dropped_as_placeholders():
    from training.data_prep.gemini_label import align

    text = "N/A , Business Administration 1999 Jefferson College"
    stats = Counter()
    entities = align(text, [{"label": "Degree", "text": "N/A"}, {"label": "College Name", "text": "Jefferson College"}], stats)
    # "1999" is added by the graduation-year rule (it is on the school's line).
    assert [(e.label, text[e.start:e.end]) for e in entities] == [
        ("Graduation Year", "1999"), ("College Name", "Jefferson College")
    ]
    assert stats["placeholder_dropped"] == 1


def _failing_then(answer, *codes: int):
    """A call that raises an API error with each code in turn, then returns `answer`."""
    from google.genai import errors

    pending = list(codes)

    def call():
        if pending:
            code = pending.pop(0)
            raise (errors.ServerError if code >= 500 else errors.ClientError)(code, {"error": {"code": code}})
        return answer

    return call


def test_rate_limits_and_server_faults_are_retried():
    from training.data_prep.gemini_label import _with_retry

    assert _with_retry(_failing_then("ok", 429, 503, 500), first_wait=0) == "ok"


def test_other_client_errors_are_not_retried():
    from google.genai import errors

    from training.data_prep.gemini_label import _with_retry

    with pytest.raises(errors.ClientError):
        _with_retry(_failing_then("ok", 400), first_wait=0)


def test_retries_stop_after_the_last_attempt():
    from google.genai import errors

    from training.data_prep.gemini_label import _with_retry

    with pytest.raises(errors.ServerError):
        _with_retry(_failing_then("ok", 503, 503, 503), attempts=3, first_wait=0)
