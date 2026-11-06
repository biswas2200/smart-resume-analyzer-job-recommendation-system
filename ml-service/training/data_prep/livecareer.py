"""Converts the LiveCareer resumes (datasets/archive/Resume/Resume.csv: 2,484
resumes in 24 job categories) into unlabelled records, the pool Gemini will
label.

Text comes from the Resume_html column, turned into lines, because the plain
Resume_str column has lost every line break and line breaks are one of the
strongest signals in a resume. Company names and candidate names are
anonymised in this dataset ("Company Name"), so labels for those types will
be sparse here.

Excluded:
- the resumes used as the unseen test set (datasets/eval-unseen/labels.jsonl),
  so the 64 % baseline is never trained on;
- exact duplicate texts (2 in the file);
- texts shorter than MIN_CHARS, which are failed exports, not resumes.
"""

import csv
import hashlib
import json
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from training.data_prep.schema import Record

SOURCE = "livecareer"
MIN_CHARS = 300

# Tags that end a line of text when the HTML is flattened.
_BLOCK_TAGS = {"div", "p", "br", "li", "tr", "h1", "h2", "h3", "h4", "ul", "table"}


class _TextCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Visible text of a LiveCareer resume, one block element per line, with
    runs of spaces collapsed and empty lines removed."""
    collector = _TextCollector()
    collector.feed(html)
    lines = (" ".join(line.split()) for line in "".join(collector.parts).splitlines())
    return "\n".join(line for line in lines if line)


def load_excluded_ids(labels_path: Path | None) -> set[str]:
    """LiveCareer IDs of the unseen test resumes, or nothing if the file is absent."""
    if labels_path is None or not labels_path.exists():
        return set()
    with open(labels_path, encoding="utf-8") as handle:
        return {json.loads(line)["id"] for line in handle if line.strip()}


def load(csv_path: Path, excluded_ids: set[str], limit: int | None = None) -> tuple[list[Record], Counter]:
    """Unlabelled records for every usable resume in the CSV (or the first
    `limit` rows), with stats."""
    csv.field_size_limit(sys.maxsize)
    stats: Counter = Counter()
    seen_hashes: set[str] = set()
    records = []
    with open(csv_path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if limit and stats["rows"] >= limit:
                break
            stats["rows"] += 1
            if row["ID"] in excluded_ids:
                stats["excluded_unseen_test"] += 1
                continue
            text = html_to_text(row["Resume_html"])
            if len(text) < MIN_CHARS:
                stats["too_short"] += 1
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in seen_hashes:
                stats["duplicate"] += 1
                continue
            seen_hashes.add(digest)
            records.append(
                Record(
                    id=f"{SOURCE}-{row['ID']}",
                    source=SOURCE,
                    split="unlabelled",
                    text=text,
                    meta={"category": row["Category"]},
                )
            )
    stats["kept"] = len(records)
    return records, stats
