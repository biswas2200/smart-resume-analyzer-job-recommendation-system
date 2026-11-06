"""Tests scripts/build_general_catalogue.py and scripts/compare_catalogues.py.
The skill filter: posting boilerplate, background checks, application
documents and degrees never become skills, while real skills, specific
credentials and soft skills survive. The build: the same postings give the same
catalogue in any order, which the BigQuery export does not fix."""

import gzip
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_general_catalogue import build, clean_skill, read_postings  # noqa: E402
from compare_catalogues import report, summary  # noqa: E402

DOMAINS = {
    "engineering": {"id": "engineering", "name": "Engineering & Technology", "engine": "local"},
    "healthcare": {"id": "healthcare", "name": "Healthcare & Life Sciences", "engine": "llm"},
    "legal": {"id": "legal", "name": "Legal", "engine": "llm"},
}


def sample_postings() -> list[tuple[str, list[str]]]:
    return (
        # Two spellings of BLS, tied 25 to 25; "patient care" is outnumbered.
        [("Registered Nurse", ["Patient Care", "BLS", "Communication"])] * 25
        + [("Registered Nurse", ["Patient Care", "Bls", "Communication"])] * 25
        + [("Senior Registered Nurse II", ["patient care", "ACLS"])] * 10
        + [("Registered Nurse", [])] * 5  # no skills: not counted
        + [("Paralegal", ["Legal Research", "Drafting", "Communication"])] * 45
        + [("Attorney", ["Litigation"])] * 39  # under the 40-posting minimum
        + [("Software Engineer", ["Python"])] * 60  # IT: served by the curated catalogue
    )


@pytest.mark.parametrize(
    "junk",
    [
        "13 weeks", "Guaranteed Hours", "Paid training", "Relocation to Madison WI", "12hour shifts",
        "Sick pay", "Career growth opportunities", "Criminal Records Check", "Working with Children Check",
        "U.S. Citizenship", "Clean driving record", "Active license", "State licensing exam",
        "Transcripts", "Teaching Philosophy", "PhD", "Doctor of Medicine", "AVMA accredited college",
        "Vomiting/diarrhea", "MLS membership",
    ],
)
def test_non_skills_are_rejected(junk):
    assert clean_skill(junk) is None


@pytest.mark.parametrize(
    "skill",
    [
        "CPR", "CPA license", "PMP Certification", "Series 7", "Real estate license", "ISO 9001",
        "AutoCAD Civil 3D", "Primavera P6", "Communication", "Heavy lifting", "Contract Management",
        "Shift Supervisor", "Portfolio Management", "Registered Nurse",
    ],
)
def test_real_skills_and_credentials_are_kept(skill):
    assert clean_skill(skill) == skill


def test_build_picks_roles_skills_and_spellings():
    roles, taxonomy = build(sample_postings(), DOMAINS)

    assert [(r["domain"], r["role"], r["source_postings"]) for r in roles] == [
        ("healthcare", "Registered Nurse", 60),
        ("legal", "Paralegal", 45),
    ]
    nurse = roles[0]
    assert nurse["description"] == "Registered Nurse roles in Healthcare & Life Sciences"
    assert "Patient Care" in nurse["skills"] and "patient care" not in nurse["skills"]
    assert "BLS" in nurse["skills"] and "Bls" not in nurse["skills"]  # a tie goes to the first alphabetically
    assert taxonomy["Patient Care"] == ["patient care"]
    assert list(taxonomy) == sorted(taxonomy)


def test_build_does_not_depend_on_posting_order():
    postings = sample_postings()
    expected = build(postings, DOMAINS)
    for seed in range(3):
        shuffled = postings[:]
        random.Random(seed).shuffle(shuffled)
        assert build(shuffled, DOMAINS) == expected


def test_read_postings_reads_every_part_in_order_and_stops_at_the_limit(tmp_path):
    for name, rows in [
        ("part-000000000001.json.gz", [{"job_title": "Paralegal", "skills": ["Drafting"]}]),
        ("part-000000000000.json.gz", [{"job_title": "Registered Nurse", "skills": ["BLS"]}, {"skills": ["CPR"]}]),
    ]:
        with gzip.open(tmp_path / name, "wt", encoding="utf-8") as f:
            f.writelines(json.dumps(row) + "\n" for row in rows)

    assert list(read_postings(tmp_path)) == [("Registered Nurse", ["BLS"]), ("", ["CPR"]), ("Paralegal", ["Drafting"])]
    assert list(read_postings(tmp_path, limit=2)) == [("Registered Nurse", ["BLS"]), ("", ["CPR"])]


def test_compare_report_lists_role_and_skill_changes(tmp_path):
    def write(folder, roles):
        folder.mkdir()
        (folder / "role_skills_general.json").write_text(json.dumps(roles))
        taxonomy = {s: [s.lower()] for r in roles for s in r["skills"]}
        (folder / "skill_taxonomy_general.json").write_text(json.dumps(taxonomy))

    nurse = {"role": "Registered Nurse", "domain": "healthcare", "skills": ["BLS", "CPR"], "source_postings": 90}
    write(tmp_path / "old", [nurse, {"role": "Cashier", "domain": "sales", "skills": ["POS"], "source_postings": 50}])
    write(tmp_path / "new", [
        {**nurse, "skills": ["BLS", "ACLS"], "source_postings": 70},
        {"role": "Account Executive", "domain": "sales", "skills": ["CRM"], "source_postings": 60},
    ])

    text = report(tmp_path / "old", tmp_path / "new")
    assert "| Roles | 2 | 2 |" in text
    assert "came in: 1; dropped out: 1" in text
    assert "| Registered Nurse | 90 → 70 | ACLS | CPR |" in text
    assert "Came in: Account Executive (60)" in text
    assert "Dropped out: Cashier (50)" in text
    assert summary(tmp_path / "old", tmp_path / "new") == (
        "2 roles (was 2): 1 came in, 1 dropped out, 1 skill lists changed (0 only reordered); "
        "taxonomy 3 -> 3 skills (+2 / -2)"
    )
