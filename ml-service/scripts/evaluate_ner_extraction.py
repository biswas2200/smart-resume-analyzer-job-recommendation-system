"""Evaluates local_ner_parser.py's entity extraction against real,
human-annotated ground truth: datasets/archive (1)/Entity Recognition in
Resumes.json (220 resumes, character-span annotations labeled Skills,
Degree, College Name, Graduation Year, Designation, Companies worked at --
the same label vocabulary local_ner_parser.py already expects).

Two modes:
  --sample N   Print our extracted ResumeProfile next to the ground-truth
               spans for N resumes, for manual eyeballing. This is the
               first thing to run -- it tells you whether the comparison
               even makes sense before trusting any number.
  --metrics    Run the full set and print precision/recall/F1 per field.

Run from ml-service/ with the venv active:
    .venv/bin/python scripts/evaluate_ner_extraction.py --sample 5
    .venv/bin/python scripts/evaluate_ner_extraction.py --metrics
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.local_ner_parser import parse_resume_local  # noqa: E402
from app.services.sectioner import split_sections  # noqa: E402
from app.services.dictionary_skills import find_skills  # noqa: E402

DATASET_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "datasets"
    / "archive (1)"
    / "Entity Recognition in Resumes.json"
)

# Ground-truth "Skills" spans are a raw block of text (e.g. "C (Less than 1
# year), Database (Less than 1 year), ..."), not individual skill names --
# same shape as our own NER "Skills" spans before _split_skill_spans() runs.
# Reused here so ground truth and our output are tokenized the same way.
_SKILL_DELIMITER_RE = re.compile(r"[,/|;•\n]+|\band\b", re.IGNORECASE)
_EXPERIENCE_SUFFIX_RE = re.compile(r"\s*\(less than \d+ year[s]?\)\s*", re.IGNORECASE)


def load_records():
    with open(DATASET_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def ground_truth_by_label(record: dict) -> dict[str, list[str]]:
    by_label: dict[str, list[str]] = {}
    for annotation in record.get("annotation", []):
        labels = annotation.get("label", [])
        for point in annotation.get("points", []):
            text = point.get("text", "").strip()
            if not text:
                continue
            for label in labels:
                by_label.setdefault(label, []).append(text)
    return by_label


def split_skill_block(block: str) -> set[str]:
    pieces = set()
    for piece in _SKILL_DELIMITER_RE.split(block):
        piece = _EXPERIENCE_SUFFIX_RE.sub("", piece).strip(" .")
        if piece:
            pieces.add(piece.lower())
    return pieces


def run_sample(n: int) -> None:
    records = load_records()[:n]
    for i, record in enumerate(records, 1):
        text = record["content"]
        gt = ground_truth_by_label(record)

        profile = parse_resume_local(text)

        print(f"\n{'=' * 70}\nRESUME {i}/{n}\n{'=' * 70}")

        print("\n--- SKILLS ---")
        gt_skills = set()
        for block in gt.get("Skills", []):
            gt_skills |= split_skill_block(block)
        print("ground truth (tokenized):", sorted(gt_skills))
        print("our extraction (canonical):", sorted(profile.skills))

        print("\n--- EDUCATION ---")
        print("ground truth Degree:", gt.get("Degree", []))
        print("ground truth College Name:", gt.get("College Name", []))
        print("ground truth Graduation Year:", gt.get("Graduation Year", []))
        print("our extraction:", [(e.degree, e.institution, e.year) for e in profile.education])

        print("\n--- EXPERIENCE ---")
        print("ground truth Designation:", gt.get("Designation", []))
        print("ground truth Companies worked at:", gt.get("Companies worked at", []))
        print("our extraction:", [(e.title, e.organization) for e in profile.experience])

        print("\n--- SECTIONING (what the NER model actually saw) ---")
        sections = split_sections(text)
        saw_sections = bool(sections.experience or sections.education)
        print("recognized headings:", saw_sections)
        if saw_sections:
            print("experience section (first 200 chars):", sections.experience[:200])
            print("education section (first 200 chars):", sections.education[:200])

        print("\n--- DICTIONARY SKILLS (whole text) ---")
        print(find_skills(text))


def _contains_either(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a) and bool(b) and (a in b or b in a)


def _field_recall(gt_values: list[str], our_values: list[str]) -> tuple[int, int]:
    """(matched_count, gt_count) for one field in one record -- a ground
    truth value counts as matched if it fuzzy-matches (substring, either
    direction) ANY of our extracted values for that field, since our parser
    may emit several education/experience entries per resume.
    """
    if not gt_values:
        return (0, 0)
    matched = sum(1 for gt in gt_values if any(_contains_either(gt, ours) for ours in our_values))
    return (matched, len(gt_values))


def evaluate_record(record: dict) -> dict:
    text = record["content"]
    gt = ground_truth_by_label(record)
    profile = parse_resume_local(text)

    gt_skill_tokens: set[str] = set()
    for block in gt.get("Skills", []):
        gt_skill_tokens |= split_skill_block(block)
    our_skills_lower = [s.lower() for s in profile.skills]
    gt_skills_text = " ".join(gt.get("Skills", [])).lower()

    skills_precision_hits = sum(1 for s in our_skills_lower if s in gt_skills_text)
    skills_recall_hits = sum(
        1 for t in gt_skill_tokens if any(_contains_either(t, s) for s in our_skills_lower)
    )

    degree_match, degree_gt = _field_recall(gt.get("Degree", []), [e.degree for e in profile.education])
    institution_match, institution_gt = _field_recall(
        gt.get("College Name", []), [e.institution for e in profile.education]
    )
    year_match, year_gt = _field_recall(gt.get("Graduation Year", []), [e.year for e in profile.education])
    designation_match, designation_gt = _field_recall(
        gt.get("Designation", []), [e.title for e in profile.experience]
    )
    company_match, company_gt = _field_recall(
        gt.get("Companies worked at", []), [e.organization for e in profile.experience]
    )

    return {
        "skills_precision_hits": skills_precision_hits,
        "skills_precision_total": len(our_skills_lower),
        "skills_recall_hits": skills_recall_hits,
        "skills_recall_total": len(gt_skill_tokens),
        "degree_match": degree_match, "degree_gt": degree_gt,
        "institution_match": institution_match, "institution_gt": institution_gt,
        "year_match": year_match, "year_gt": year_gt,
        "designation_match": designation_match, "designation_gt": designation_gt,
        "company_match": company_match, "company_gt": company_gt,
    }


def _rate(match: int, total: int) -> str:
    return f"{match}/{total} ({match / total:.1%})" if total else "n/a (no ground truth)"


def run_metrics() -> None:
    records = load_records()
    totals = {
        k: 0
        for k in (
            "skills_precision_hits", "skills_precision_total", "skills_recall_hits", "skills_recall_total",
            "degree_match", "degree_gt", "institution_match", "institution_gt",
            "year_match", "year_gt", "designation_match", "designation_gt",
            "company_match", "company_gt",
        )
    }

    for i, record in enumerate(records, 1):
        result = evaluate_record(record)
        for k, v in result.items():
            totals[k] += v
        if i % 20 == 0:
            print(f"...{i}/{len(records)} processed", file=sys.stderr)

    print(f"\n=== Entity extraction baseline over {len(records)} resumes ===\n")
    print("Skills")
    print(f"  precision (our skills confirmed by GT text): {_rate(totals['skills_precision_hits'], totals['skills_precision_total'])}")
    print(f"  recall (GT skill tokens we found):           {_rate(totals['skills_recall_hits'], totals['skills_recall_total'])}")
    print("  note: GT recall denominator includes some header/noise tokens from whole-paragraph annotation spans")
    print()
    print("Education (recall -- fraction of ground-truth values our parser matched)")
    print(f"  Degree:      {_rate(totals['degree_match'], totals['degree_gt'])}")
    print(f"  Institution: {_rate(totals['institution_match'], totals['institution_gt'])}")
    print(f"  Grad. year:  {_rate(totals['year_match'], totals['year_gt'])}")
    print()
    print("Experience (recall -- fraction of ground-truth values our parser matched)")
    print(f"  Designation: {_rate(totals['designation_match'], totals['designation_gt'])}")
    print(f"  Company:     {_rate(totals['company_match'], totals['company_gt'])}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="Print N resumes for manual review")
    parser.add_argument("--metrics", action="store_true", help="Run the full set and print P/R per field")
    args = parser.parse_args()

    if args.sample:
        run_sample(args.sample)
    elif args.metrics:
        run_metrics()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
