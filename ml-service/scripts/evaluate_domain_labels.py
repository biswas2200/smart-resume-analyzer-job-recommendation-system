"""Score the app's domain classifier (services/domain_classifier.py) against labelled resumes.

The labels come from training/data_prep/gemini_label_domain.py (JSONL: id, category, domain,
alt_domain, job_title, confidence, reason). Each resume is read from its PDF the way the app reads
it, so this measures what a user would get.

    python scripts/evaluate_domain_labels.py ../datasets/labelled/domains.gemini-3.8-flash.v1.jsonl
    python scripts/evaluate_domain_labels.py LABELS.jsonl --pdf-dir ../datasets/archive/data/data --misses 15
    python scripts/evaluate_domain_labels.py LABELS.jsonl --only-confident     # skip low-confidence labels

Reports exact agreement, agreement counting the labeller's second field, agreement by labeller
confidence, per-field recall, and the most frequent confusions. Run it from ml-service/ with the
virtualenv active (it loads the embedding model).
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_PDF_DIR = ROOT.parent / "datasets" / "archive" / "data" / "data"


def load_labels(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", type=Path)
    ap.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    ap.add_argument("--only-confident", action="store_true", help="drop labels the labeller marked low")
    ap.add_argument("--misses", type=int, default=10, help="how many disagreements to print")
    ap.add_argument("--detail", action="store_true", help="print every resume")
    args = ap.parse_args()

    from app.services import domain_classifier
    from app.services.document_extraction.registry import get_extractor_for_filename

    rows = [r for r in load_labels(args.labels) if not (args.only_confident and r["confidence"] == "low")]
    exact = either = 0
    by_conf: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    recall: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    confusion: collections.Counter = collections.Counter()
    misses = []
    for row in rows:
        category, stem = row["id"].split("/", 1)
        path = args.pdf_dir / category / f"{stem}.pdf"
        text = get_extractor_for_filename(path.name).extract(path.read_bytes()).text
        predicted = domain_classifier.detect_domain(text).domain
        ok = predicted == row["domain"]
        also = ok or predicted == row.get("alt_domain")
        exact += ok
        either += also
        by_conf[row["confidence"]][0] += ok
        by_conf[row["confidence"]][1] += 1
        recall[row["domain"]][0] += ok
        recall[row["domain"]][1] += 1
        if not ok:
            confusion[(row["domain"], predicted)] += 1
            misses.append((row, predicted))
        if args.detail:
            print(f"{'ok ' if ok else 'MISS'} {row['id']:34} label={row['domain']:26} predicted={predicted}")

    n = len(rows)
    print(f"{n} labelled resumes")
    print(f"exact agreement with the label:            {exact}/{n} = {exact * 100 // n}%")
    print(f"agreement counting the label's 2nd field:   {either}/{n} = {either * 100 // n}%")
    print("by labeller confidence: " + ", ".join(
        f"{c} {ok}/{total} ({ok * 100 // total}%)" for c, (ok, total) in sorted(by_conf.items())))
    print("\nrecall per labelled field (n >= 3):")
    for field, (ok, total) in sorted(recall.items(), key=lambda x: -x[1][1]):
        if total >= 3:
            print(f"  {field:30} {ok}/{total} ({ok * 100 // total}%)")
    print("\nmost frequent confusions (labelled -> predicted):")
    for (label, predicted), count in confusion.most_common(8):
        print(f"  {count:3}  {label} -> {predicted}")
    if args.misses:
        print(f"\nfirst {args.misses} disagreements:")
        for row, predicted in misses[: args.misses]:
            print(f"  {row['id']}: label {row['domain']} ({row['confidence']}, '{row['job_title']}') vs predicted {predicted}"
                  f"\n      reason: {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
