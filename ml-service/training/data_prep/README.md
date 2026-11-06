# Data preparation

Turns the raw resume datasets into one common record format, then into BIO
training files for the NER model. Standard library only: it runs on the laptop
(about 3 seconds, under 60 MB of RAM for the resume data) or unchanged on a GCP
VM ([../gcp-setup.md](../gcp-setup.md)).

```bash
cd ml-service
python -m training.data_prep.build --datasets-dir ../datasets --out ../datasets/prepared
python -m training.data_prep.build --datasets-dir ../datasets --out /tmp/smoke --limit 20   # quick check
```

`--datasets-dir` must have the laptop's `datasets/` layout. Output goes under
`--out`; `datasets/` is git-ignored, so prepared data never gets committed.

## Files

| File | What it does |
|---|---|
| `schema.py` | The record format, the model's 25 BIO labels in model order, and `validate_record` |
| `dataturks.py` | DataTurks (220 labelled Indeed resumes): fixes offsets, trims spaces, resolves overlaps, assigns splits |
| `livecareer.py` | LiveCareer `Resume.csv` (2,484 resumes, 24 fields): HTML to text, the unlabelled pool for Gemini labelling (`gemini-3.5-flash-lite`) |
| `bio.py` | A labelled record as one tag per word |
| `build.py` | Runs everything, validates, writes the files and `report.json` |
| `gemini_label.py` | Labels the unlabelled pool with `gemini-3.5-flash-lite` (prompt v3); read [LABELLING.md](LABELLING.md) first |

## The record format

One resume per JSON line. `end` is exclusive, so `text[start:end]` is the
entity:

```json
{"id": "dataturks-0001", "source": "dataturks", "split": "train",
 "text": "Abhishek Jha\nApplication Development Associate - Accenture ...",
 "entities": [{"start": 0, "end": 12, "label": "Name"}], "meta": {}}
```

## Splits

| Split | Resumes | Why |
|---|---|---|
| `train` | DataTurks 1 to 100 | Training |
| `dev` | DataTurks 101 to 110 | Choosing when to stop training |
| `test` | DataTurks 111 to 220 | The same held-out half the 60 % baseline was measured on, so a retrained model is compared like for like |
| `unlabelled` | 2,461 LiveCareer resumes | Input for labelling with `gemini-3.5-flash-lite` |

The 20 LiveCareer resumes in `datasets/eval-unseen/` (the 64 % baseline) are
excluded from the pool, so they are never trained on.

## What the cleaning fixes (last full run)

| Problem in the raw data | Count | Fix |
|---|---|---|
| Annotated text not at the stated position | 217 | Nearest occurrence of the same text |
| Annotated text nowhere in the resume | 4 | Dropped |
| Spaces or newlines at a span's edges | 663 | Trimmed |
| Overlapping spans (13 exact duplicates, 103 nested) | 116 | Longer span kept |
| `UNKNOWN` label, or no label | 4 | Dropped |
| LiveCareer duplicate texts / too short | 2 / 1 | Dropped |

Result: 3,434 labelled entities in 220 resumes, and 2,461 resumes to label.

Some DataTurks labels are simply wrong (an Indeed profile URL tagged as an
email address, "SAP ABAP" tagged as a company). Rules cannot fix those; the
Gemini relabelling step and the dev/test scores are where they show up.

## How correctness is checked

- `tests/test_data_prep.py`: one small hand-built case per cleaning rule, with
  the expected output written down before running it; plus a check that the
  label list matches the cached model's `config.json`.
- `build.py` validates every record (spans inside the text, no edge
  whitespace, no overlaps, known labels and splits) and writes nothing if any
  record fails.
- After a full run, the counts in `report.json` should reconcile:
  labelled spans minus not found, dropped labels and overlaps equals
  `entities_kept`, and LiveCareer rows minus exclusions equals `kept`.
