"""Converts the DataTurks resume NER file (datasets/archive (1)/Entity
Recognition in Resumes.json: 220 Indeed resumes, one JSON object per line)
into common records.

The raw annotations have four problems, each counted in the stats:

- offset_repaired: the annotated text exists in the resume, but not at the
  stated position (219 spans). The nearest occurrence is used.
- not_found: the annotated text is nowhere in the resume (4 spans). Dropped.
- whitespace_trimmed: the span starts or ends with spaces or newlines (719).
- overlap_dropped: two spans overlap, mostly one nested in another
  ("oracle" inside "oracle India Limited"). The longer span is kept.

Splits follow the file order the baseline was measured with
(scripts/evaluate_ner_extraction.py and the parser A/B run): resumes 1-110
were used for tuning, 111-220 are the held-out test set. Training uses 1-100,
101-110 is the dev set, and 111-220 stays test so a retrained model is
compared on the same resumes as the 60 % baseline.
"""

import json
from collections import Counter
from pathlib import Path

from training.data_prep.schema import ENTITY_TYPES, Entity, Record

SOURCE = "dataturks"
TRAIN_END = 100  # resumes 1-100
DEV_END = 110  # resumes 101-110; 111-220 are test

# DataTurks already uses the model's label names. UNKNOWN (2 spans) carries
# no meaning worth teaching, so it is dropped rather than mapped.
DROPPED_LABELS = {"UNKNOWN"}


def split_for(position: int) -> str:
    """Split for the resume at 1-based `position` in the file."""
    if position <= TRAIN_END:
        return "train"
    return "dev" if position <= DEV_END else "test"


def locate(text: str, start: int, end_inclusive: int, annotated: str) -> tuple[int, int] | None:
    """The (start, end-exclusive) span of `annotated` in `text`: the stated
    position when it matches, otherwise the occurrence nearest to it. None
    when the annotated text appears nowhere.
    """
    if text[start:end_inclusive + 1] == annotated:
        return start, end_inclusive + 1
    needle = annotated.strip()
    if not needle:
        return None
    best = None
    position = text.find(needle)
    while position != -1:
        if best is None or abs(position - start) < abs(best - start):
            best = position
        position = text.find(needle, position + 1)
    return None if best is None else (best, best + len(needle))


def trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink a span so it neither starts nor ends with whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def drop_overlaps(entities: list[Entity]) -> tuple[list[Entity], int]:
    """Keep the longest spans first and drop any span that overlaps one
    already kept. Returns the kept spans in text order and how many were
    dropped."""
    kept: list[Entity] = []
    for entity in sorted(entities, key=lambda e: (-(e.end - e.start), e.start)):
        if all(entity.end <= k.start or entity.start >= k.end for k in kept):
            kept.append(entity)
    return sorted(kept, key=lambda e: e.start), len(entities) - len(kept)


def convert(raw: dict, position: int, stats: Counter) -> Record:
    """One DataTurks JSON object (the resume at 1-based `position`) as a Record."""
    text = raw["content"]
    entities = []
    for annotation in raw.get("annotation") or []:
        labels = annotation.get("label") or []
        if not labels:
            stats["no_label_dropped"] += 1
            continue
        label = labels[0]
        for point in annotation.get("points", []):
            if label in DROPPED_LABELS or label not in ENTITY_TYPES:
                stats["label_dropped"] += 1
                continue
            span = locate(text, point["start"], point["end"], point["text"])
            if span is None:
                stats["not_found"] += 1
                continue
            if span[0] != point["start"]:
                stats["offset_repaired"] += 1
            start, end = trim(text, *span)
            if (start, end) != span:
                stats["whitespace_trimmed"] += 1
            if start == end:
                stats["empty_dropped"] += 1
                continue
            entities.append(Entity(start, end, label))

    entities, dropped = drop_overlaps(entities)
    stats["overlap_dropped"] += dropped
    stats["entities_kept"] += len(entities)
    return Record(
        id=f"{SOURCE}-{position:04d}",
        source=SOURCE,
        split=split_for(position),
        text=text,
        entities=entities,
    )


def load(path: Path, limit: int | None = None) -> tuple[list[Record], Counter]:
    """Every resume in the DataTurks file (or the first `limit`), with stats."""
    stats: Counter = Counter()
    records = []
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle if line.strip()]
    for position, line in enumerate(lines[:limit] if limit else lines, start=1):
        records.append(convert(json.loads(line), position, stats))
    stats["resumes"] = len(records)
    return records, stats
