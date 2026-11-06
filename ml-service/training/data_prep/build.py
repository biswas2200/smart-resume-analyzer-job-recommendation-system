"""Builds every prepared file from the raw datasets in one run.

    cd ml-service
    python -m training.data_prep.build --datasets-dir ../datasets --out ../datasets/prepared
    python -m training.data_prep.build --datasets-dir ../datasets --out /tmp/smoke --limit 20

--datasets-dir must have the laptop's datasets/ layout (the GCP upload keeps
it). Output:

    records/dataturks.jsonl              labelled, splits train/dev/test
    records/livecareer_unlabelled.jsonl  the pool for Gemini labelling
    bio/{train,dev,test}.jsonl           BIO files built from labelled records
    report.json                          everything the summary prints

Nothing is written if any record fails validation; the problems are printed
and the exit code is 1.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from training.data_prep import dataturks, livecareer
from training.data_prep.bio import to_bio
from training.data_prep.schema import Record, validate_record

DATATURKS_PATH = Path("archive (1)") / "Entity Recognition in Resumes.json"
LIVECAREER_PATH = Path("archive") / "Resume" / "Resume.csv"
UNSEEN_LABELS_PATH = Path("eval-unseen") / "labels.jsonl"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build(datasets_dir: Path, out_dir: Path, limit: int | None = None) -> dict:
    """Convert, validate and write everything. Returns the report; raises
    ValueError (writing nothing) if any record is invalid."""
    turks, turks_stats = dataturks.load(datasets_dir / DATATURKS_PATH, limit)
    excluded = livecareer.load_excluded_ids(datasets_dir / UNSEEN_LABELS_PATH)
    career, career_stats = livecareer.load(datasets_dir / LIVECAREER_PATH, excluded, limit)

    problems = [p for record in [*turks, *career] for p in validate_record(record)]
    if problems:
        raise ValueError("\n".join(problems))

    labelled: list[Record] = turks
    bio_by_split: dict[str, list[dict]] = {"train": [], "dev": [], "test": []}
    for record in labelled:
        bio_by_split[record.split].append(to_bio(record))

    write_jsonl(out_dir / "records" / "dataturks.jsonl", [r.to_dict() for r in turks])
    write_jsonl(out_dir / "records" / "livecareer_unlabelled.jsonl", [r.to_dict() for r in career])
    for split, rows in bio_by_split.items():
        write_jsonl(out_dir / "bio" / f"{split}.jsonl", rows)

    report = {
        "dataturks": dict(turks_stats),
        "livecareer": dict(career_stats),
        "unseen_test_ids_excluded": len(excluded),
        "resumes_per_split": dict(Counter(r.split for r in [*turks, *career])),
        "entities_per_label": dict(Counter(e.label for r in labelled for e in r.entities).most_common()),
        "livecareer_categories": len({r.meta["category"] for r in career}),
        "bio": {
            split: {
                "resumes": len(rows),
                "words": sum(len(r["tokens"]) for r in rows),
                "entity_words": sum(t != "O" for r in rows for t in r["ner_tags"]),
            }
            for split, rows in bio_by_split.items()
        },
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--datasets-dir", type=Path, required=True, help="folder with the raw datasets")
    parser.add_argument("--out", type=Path, required=True, help="output folder")
    parser.add_argument("--limit", type=int, help="only the first N resumes of each dataset (smoke runs)")
    args = parser.parse_args()
    try:
        report = build(args.datasets_dir, args.out, args.limit)
    except ValueError as error:
        print("Validation failed, nothing written:\n" + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
