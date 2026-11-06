"""Tests the answer-key tooling in training/evaluate_model.py: corrections
applied to the right resume, and the worksheet listing what the key lacks."""

from types import SimpleNamespace

from training.evaluate_model import TURKS_FIELDS, apply_fixes, disputes, score

TEXT = "Senior Service Engineer\nDell EMC - Bangalore\nSystems Engineer\nIBM"


def _profile(*titles: str, companies: tuple = ()) -> SimpleNamespace:
    jobs = [SimpleNamespace(title=t, organization=c) for t, c in zip(titles, [*companies, *[""] * len(titles)])]
    return SimpleNamespace(name="", education=[], experience=jobs)


def test_fixes_add_and_remove_values_on_the_named_resume_only():
    turks = [(TEXT, {"Designation": ["Senior Service Engineer"], "Companies worked at": ["SAP ABAP"]}),
             ("other", {"Designation": ["Clerk"]})]
    fixes = {"dataturks-0111": {"Job title": {"add": ["Systems Engineer"]},
                                "Company": {"add": ["Dell EMC"], "remove": ["SAP ABAP"]}}}

    fixed = apply_fixes(turks, fixes)

    assert fixed[0][1]["Designation"] == ["Senior Service Engineer", "Systems Engineer"]
    assert fixed[0][1]["Companies worked at"] == ["Dell EMC"]
    assert fixed[1][1] == {"Designation": ["Clerk"]}
    assert turks[0][1]["Designation"] == ["Senior Service Engineer"]          # the original is untouched


def test_a_found_value_added_to_the_key_raises_precision():
    turks = [(TEXT, {"Designation": ["Senior Service Engineer"]})]
    parse = lambda _text: _profile("Senior Service Engineer", "Systems Engineer")

    before = score(parse, turks, {"Job title": TURKS_FIELDS["Job title"]})["Job title"]
    after = score(parse, apply_fixes(turks, {"dataturks-0111": {"Job title": {"add": ["Systems Engineer"]}}}),
                  {"Job title": TURKS_FIELDS["Job title"]})["Job title"]

    assert (before["precision"], after["precision"]) == (0.5, 1.0)


def test_worksheet_lists_values_outside_the_key_with_their_models_and_lines():
    turks = [(TEXT, {"Designation": ["Senior Service Engineer", "Chief Pilot"]})]
    outputs = {"old": [_profile("Senior Service Engineer", "Engineer")],
               "new": [_profile("Senior Service Engineer", "Systems Engineer")]}

    rows = disputes(outputs, turks, {"Job title": TURKS_FIELDS["Job title"]})

    assert len(rows) == 1 and rows[0]["id"] == "dataturks-0111"
    extra = {e["value"]: e for e in rows[0]["extra"]}
    assert set(extra) == {"Systems Engineer"}     # "Engineer" is inside a key value, so it already matches
    assert extra["Systems Engineer"]["models"] == ["new"]
    assert "Systems Engineer" in extra["Systems Engineer"]["context"]
    assert [m["value"] for m in rows[0]["missed_by_all"]] == ["Chief Pilot"]
    assert rows[0]["missed_by_all"][0]["context"] == "(not verbatim in the resume)"


def test_line_breaks_inside_a_key_value_do_not_stop_a_match():
    turks = [(TEXT, {"Companies worked at": ["Wipro\nTechnologies."]})]
    parse = lambda _text: _profile("Engineer", companies=("Wipro Technologies",))

    result = score(parse, turks, {"Company": TURKS_FIELDS["Company"]})["Company"]

    assert result["precision"] == result["recall"] == 1.0
