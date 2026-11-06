"""The common record format every dataset is converted into, and the checks a
record must pass before it is written.

One record per resume, stored as one JSON line:

    {"id": "dataturks-0001", "source": "dataturks", "split": "train",
     "text": "Abhishek Jha\\nApplication Development Associate - Accenture ...",
     "entities": [{"start": 0, "end": 12, "label": "Name"}, ...],
     "meta": {}}

`end` is exclusive, like Python slicing: text[start:end] is the entity text.
DataTurks itself stores an inclusive end; its converter does the translation.
"""

from dataclasses import asdict, dataclass, field

# The 12 entity types of the NER model (yashpwr/resume-ner-bert), in the order
# of its config.json id2label. The BIO label list below must match that order
# exactly, or a training run would teach label 3 under the wrong name.
ENTITY_TYPES = (
    "College Name",
    "Companies worked at",
    "Degree",
    "Designation",
    "Email Address",
    "Graduation Year",
    "Location",
    "Name",
    "Phone",
    "Skills",
    "UNKNOWN",
    "Years of Experience",
)

# "O" plus B-/I- for every type: the model's 25 output labels.
LABEL_LIST = ["O"] + [f"{prefix}-{entity}" for entity in ENTITY_TYPES for prefix in ("B", "I")]

SPLITS = ("train", "dev", "test", "unlabelled")


@dataclass
class Entity:
    start: int
    end: int
    label: str


@dataclass
class Record:
    id: str
    source: str
    split: str
    text: str
    entities: list[Entity] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        return cls(
            id=data["id"],
            source=data["source"],
            split=data["split"],
            text=data["text"],
            entities=[Entity(**e) for e in data.get("entities", [])],
            meta=data.get("meta", {}),
        )


def validate_record(record: Record) -> list[str]:
    """Every problem with a record, as readable strings; an empty list means
    the record is safe to train on. build.py refuses to write output when any
    record has a problem, so a bad converter fails loudly, not silently.
    """
    problems = []
    if record.split not in SPLITS:
        problems.append(f"{record.id}: unknown split {record.split!r}")
    if not record.text.strip():
        problems.append(f"{record.id}: empty text")

    previous_end = 0
    for entity in sorted(record.entities, key=lambda e: e.start):
        where = f"{record.id} [{entity.start}:{entity.end}] {entity.label}"
        if entity.label not in ENTITY_TYPES:
            problems.append(f"{where}: unknown label")
        if not 0 <= entity.start < entity.end <= len(record.text):
            problems.append(f"{where}: span outside the text")
            continue
        span = record.text[entity.start:entity.end]
        if span != span.strip():
            problems.append(f"{where}: whitespace at the span edge")
        if entity.start < previous_end:
            problems.append(f"{where}: overlaps the previous entity")
        previous_end = max(previous_end, entity.end)
    return problems
