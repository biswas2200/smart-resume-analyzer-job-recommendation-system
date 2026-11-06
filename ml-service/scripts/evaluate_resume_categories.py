"""Measure how the local pipeline (no LLM at all) reads real resumes from every job field.

Runs services/pipeline.py over PDFs from the LiveCareer resume set
(datasets/archive/data/data/<CATEGORY>/*.pdf, 24 categories, not in git) with the narrative
forced to the deterministic template, so nothing leaves the machine, and prints:

- how often a job, a degree and a college were found, and how many skills and role matches;
- sentence-like "job titles" (the model's half-tagged fragments), which should stay at 0;
- how often the detected domain agrees with the resume's own category. The category labels are
  loose (the "HEALTHCARE" folder holds pharma sales reps and BI analysts), so treat that figure as
  a trend to compare between code versions, not as accuracy.

The dataset is anonymised: no names, no contact details and "Company Name" in place of employers,
so those fields read low by construction.

    python scripts/evaluate_resume_categories.py                    # 8 PDFs per category
    python scripts/evaluate_resume_categories.py --per-category 20 --seed 3
    python scripts/evaluate_resume_categories.py --category HR --show 3   # print what was read

Run from ml-service/ with its virtualenv active (it loads the NER model; about a second a resume).
"""

from __future__ import annotations

import argparse
import collections
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DATASET = ROOT.parent / "datasets" / "archive" / "data" / "data"

# The domains a category may reasonably land in (lenient on purpose: the labels are loose).
ACCEPTED_DOMAINS: dict[str, set[str]] = {
    "ACCOUNTANT": {"finance_accounting"},
    "ADVOCATE": {"legal"},
    "AGRICULTURE": {"veterinary_agriculture", "science_research"},
    "APPAREL": {"retail_ecommerce", "design_creative", "manufacturing_production"},
    "ARTS": {"design_creative", "education"},
    "AUTOMOBILE": {"manufacturing_production", "core_engineering", "retail_ecommerce", "operations_supply_chain"},
    "AVIATION": {"operations_supply_chain", "core_engineering", "customer_service_hospitality"},
    "BANKING": {"banking_insurance", "finance_accounting"},
    "BPO": {"customer_service_hospitality", "administration"},
    "BUSINESS-DEVELOPMENT": {"sales", "marketing"},
    "CHEF": {"customer_service_hospitality"},
    "CONSTRUCTION": {"construction_trades", "core_engineering"},
    "CONSULTANT": {"consulting_project_management"},
    "DESIGNER": {"design_creative"},
    "DIGITAL-MEDIA": {"marketing", "design_creative"},
    "ENGINEERING": {"core_engineering", "engineering"},
    "FINANCE": {"finance_accounting", "banking_insurance"},
    "FITNESS": {"healthcare", "customer_service_hospitality"},
    "HEALTHCARE": {"healthcare"},
    "HR": {"human_resources"},
    "INFORMATION-TECHNOLOGY": {"engineering"},
    "PUBLIC-RELATIONS": {"marketing"},
    "SALES": {"sales"},
    "TEACHER": {"education"},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="folder with one sub-folder of PDFs per category")
    ap.add_argument("--per-category", type=int, default=8)
    ap.add_argument("--category", help="only this category (e.g. HR)")
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--show", type=int, default=0, help="print what was read for this many resumes per category")
    args = ap.parse_args()
    if not args.dataset.is_dir():
        print(f"dataset folder not found: {args.dataset}", file=sys.stderr)
        return 2

    # Imported late: they load the NER model and the embedding model.
    from app.services import local_ner_parser, pipeline
    from app.services.document_extraction.registry import get_extractor_for_filename

    original_explain = pipeline.explain_results
    pipeline.explain_results = lambda *a, **k: original_explain(*a, **{**k, "backend": "template"})

    random.seed(args.seed)
    totals: collections.Counter = collections.Counter()
    seconds = 0.0
    categories = sorted(d.name for d in args.dataset.iterdir() if d.is_dir())
    for category in categories:
        if args.category and category != args.category.upper():
            continue
        files = sorted((args.dataset / category).glob("*.pdf"))
        random.shuffle(files)
        shown = 0
        for path in files[: args.per_category]:
            try:
                text = get_extractor_for_filename(path.name).extract(path.read_bytes()).text
            except Exception:  # an unreadable PDF is not what is measured here
                continue
            started = time.perf_counter()
            result = pipeline.analyze_text(text, top_n=5)
            seconds += time.perf_counter() - started
            jobs, education = result.profile.experience, result.profile.education
            totals["resumes"] += 1
            totals["locked"] += result.recommendations_locked
            totals["has_job"] += bool(jobs)
            totals["jobs"] += len(jobs)
            totals["sentence_titles"] += sum(local_ner_parser._looks_like_phrase(j.title) for j in jobs)
            totals["has_degree"] += bool(education)
            totals["degrees"] += len(education)
            totals["degrees_with_college"] += sum(bool(e.institution) for e in education)
            totals["skills"] += len(result.profile.skills)
            totals["five_roles"] += len(result.matches) == 5
            totals["domain_agrees"] += result.domain.domain in ACCEPTED_DOMAINS.get(category, set())
            if shown < args.show:
                shown += 1
                print(f"## {category}/{path.name}: {result.domain.domain} ({result.domain.confidence})")
                print("   jobs:", [(j.title, j.organization, j.duration) for j in jobs][:4])
                print("   degrees:", [(e.degree[:40], e.institution, e.year) for e in education])
                print("   skills:", result.profile.skills[:12])
                print("   roles:", [(m.role, round(m.score, 2)) for m in result.matches[:3]])

    n = totals["resumes"]
    if not n:
        print("no resumes read", file=sys.stderr)
        return 2
    pct = lambda part, whole: f"{part * 100 // max(whole, 1)}%"  # noqa: E731
    print(f"\n{n} resumes, {seconds / n:.2f}s each, {totals['locked']} locked")
    print(f"a job found:      {pct(totals['has_job'], n)}   ({totals['jobs'] / n:.1f} per resume, "
          f"{totals['sentence_titles']} sentence-like titles)")
    print(f"a degree found:   {pct(totals['has_degree'], n)}   ({totals['degrees'] / n:.1f} per resume, "
          f"{pct(totals['degrees_with_college'], totals['degrees'])} with a college)")
    print(f"skills per resume: {totals['skills'] / n:.1f}   five role matches: {pct(totals['five_roles'], n)}")
    print(f"detected domain agrees with the category: {pct(totals['domain_agrees'], n)} (loose labels: a trend, not accuracy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
