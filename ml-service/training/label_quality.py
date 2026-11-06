"""Finds training resumes whose labels are probably wrong: the "spam filter"
for labels, using confident learning (Northcutt et al. 2021, the idea behind
the cleanlab library).

    python -m training.label_quality --bio TRAINING_DIR/bio/train.jsonl --oof OUT/folds/oof_probs.jsonl \
        --exclude-in OUT/excluded.round1.txt --out OUT/round2

Input: out-of-fold probabilities from `train_ner.py folds`. Every resume was
scored by a model that never saw its labels.

1. Per-class threshold: the average confidence the model gives each label on
   words that carry that label.
2. A word is suspect when its given label scores below that label's threshold
   while another label scores at or above its own. Missed entities (given O,
   model confident it is a title) and wrong entities both count.
3. A resume's score is the share of its suspect words among its
   entity-bearing words. The worst are removed, capped at --max-remove of
   the set per round and --max-total over all rounds: removing too much
   throws away correct but unusual resumes and narrows what the model learns.

Writes excluded.txt (cumulative ids, for train_ner.py --exclude) and
review.md (the flagged resumes with their suspect words, for a person to check).
Whether a round helped is decided by retraining and comparing dev F1; see
training/README.md.
"""

import argparse
import json
import sys
from pathlib import Path

from training.data_prep.schema import LABEL_LIST

LABEL_INDEX = {label: i for i, label in enumerate(LABEL_LIST)}


def class_thresholds(rows: list[dict], probs: dict[str, list]) -> list[float]:
    """Mean self-confidence per label over words carrying it (1.0 if unseen)."""
    sums, counts = [0.0] * len(LABEL_LIST), [0] * len(LABEL_LIST)
    for row in rows:
        for tag, p in zip(row["ner_tags"], probs[row["id"]]):
            if p is None:
                continue
            j = LABEL_INDEX[tag]
            sums[j] += p[j]
            counts[j] += 1
    return [s / c if c else 1.0 for s, c in zip(sums, counts)]


def suspect_words(row: dict, word_probs: list, thresholds: list[float]) -> list[tuple[int, str, str, float]]:
    """(word index, given label, suggested label, its probability) per suspect word."""
    found = []
    for i, (tag, p) in enumerate(zip(row["ner_tags"], word_probs)):
        if p is None:
            continue
        given = LABEL_INDEX[tag]
        if p[given] >= thresholds[given]:
            continue
        rivals = [(p[k], k) for k in range(len(p)) if k != given and p[k] >= thresholds[k]]
        if rivals:
            score, k = max(rivals)
            found.append((i, tag, LABEL_LIST[k], score))
    return found


def resume_score(row: dict, word_probs: list, suspects: list) -> float:
    """Suspect words as a share of the words that are, or are predicted to be,
    part of an entity, so long resumes are not penalised for their length."""
    entity_words = sum(1 for tag, p in zip(row["ner_tags"], word_probs)
                       if tag != "O" or (p is not None and max(range(len(p)), key=p.__getitem__) != 0))
    return len(suspects) / max(entity_words, 1)


def select(scores: dict[str, float], already: set[str], total: int, max_remove: float, max_total: float,
           min_score: float) -> list[str]:
    """Worst-scoring resumes first, within both caps and above min_score."""
    budget = min(int(max_remove * total), int(max_total * total) - len(already))
    ranked = sorted((s, i) for i, s in scores.items() if i not in already and s >= min_score)
    return [i for _, i in reversed(ranked)][:max(budget, 0)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bio", type=Path, required=True)
    parser.add_argument("--oof", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude-in", type=Path, help="ids removed in earlier rounds")
    parser.add_argument("--max-remove", type=float, default=0.05, help="share removed this round (default 5 %%)")
    parser.add_argument("--max-total", type=float, default=0.15, help="share removed over all rounds (default 15 %%)")
    parser.add_argument("--min-score", type=float, default=0.2, help="never remove a resume scoring below this")
    args = parser.parse_args()

    already = set(args.exclude_in.read_text().split()) if args.exclude_in else set()
    with open(args.bio, encoding="utf-8") as handle:
        rows = [r for r in (json.loads(line) for line in handle if line.strip())]
    with open(args.oof, encoding="utf-8") as handle:
        probs = {r["id"]: r["probs"] for r in (json.loads(line) for line in handle if line.strip())}
    rows = [r for r in rows if r["id"] in probs]
    thresholds = class_thresholds(rows, probs)
    suspects = {r["id"]: suspect_words(r, probs[r["id"]], thresholds) for r in rows}
    scores = {r["id"]: resume_score(r, probs[r["id"]], suspects[r["id"]]) for r in rows}
    chosen = select(scores, already, len(rows) + len(already), args.max_remove, args.max_total, args.min_score)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "excluded.txt").write_text("\n".join(sorted(already | set(chosen))) + "\n")
    by_id = {r["id"]: r for r in rows}
    lines = [f"# Label review: {len(chosen)} resumes removed this round, {len(already) + len(chosen)} in total",
             "", f"{len(rows)} scored. Per-class thresholds: " + ", ".join(
                 f"{label} {t:.2f}" for label, t in zip(LABEL_LIST, thresholds) if t < 1.0), ""]
    for rid in chosen:
        row = by_id[rid]
        lines += [f"## {rid}: score {scores[rid]:.2f}, {len(suspects[rid])} suspect words", "",
                  "| word | given | model suggests | p |", "|---|---|---|---|"]
        lines += [f"| {row['tokens'][i]} | {g} | {s} | {p:.2f} |" for i, g, s, p in suspects[rid][:25]]
        lines.append("")
    (args.out / "review.md").write_text("\n".join(lines), encoding="utf-8")
    summary = {"scored": len(rows), "removed_this_round": len(chosen),
               "removed_total": len(already) + len(chosen),
               "mean_score": sum(scores.values()) / max(len(scores), 1)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
