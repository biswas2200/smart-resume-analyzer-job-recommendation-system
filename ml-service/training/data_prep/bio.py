"""Turns a labelled record into BIO training data: one tag per word.

    {"id": "dataturks-0001", "tokens": ["Abhishek", "Jha", "Application", ...],
     "ner_tags": ["B-Name", "I-Name", "B-Designation", ...]}

Words here are a simple, model-independent split: runs of word characters
(keeping "B.Tech", "C++", "C#", "e-mail" whole) and single punctuation marks.
The training script re-tokenises each word into BERT subwords and labels
only the first subword, so these files work for the teacher and any student
model. Long resumes are cut into 512-token windows at training time, where
the real tokenizer is known, not here.
"""

import re

from training.data_prep.schema import LABEL_LIST, Record

WORD_RE = re.compile(r"\w+(?:[.'’&/+#-]\w+)*[+#]*|[^\w\s]")


def to_bio(record: Record) -> dict:
    """BIO tokens and tags for one record. A word belongs to an entity when the
    word starts inside it; the first such word is B-, the rest I-."""
    entities = sorted(record.entities, key=lambda e: e.start)
    tokens, tags = [], []
    index = 0
    current = None  # the entity the previous word belonged to
    for match in WORD_RE.finditer(record.text):
        start = match.start()
        while index < len(entities) and entities[index].end <= start:
            index += 1
        entity = entities[index] if index < len(entities) and entities[index].start <= start else None
        if entity is None:
            tag = "O"
        else:
            tag = f"{'I' if entity is current else 'B'}-{entity.label}"
        tokens.append(match.group())
        tags.append(tag)
        current = entity
    unknown = set(tags) - set(LABEL_LIST)
    if unknown:
        raise ValueError(f"{record.id}: tags outside the model's label list: {sorted(unknown)}")
    return {"id": record.id, "tokens": tokens, "ner_tags": tags}
