# Publishing our NER model on Hugging Face

Plan agreed in principle on 2026-10-10. **Published 2026-10-22** (public):
[`biswas2200/resume-ner-bert-careeros`](https://huggingface.co/biswas2200/resume-ner-bert-careeros) (teacher) and
[`biswas2200/resume-ner-distilbert-careeros`](https://huggingface.co/biswas2200/resume-ner-distilbert-careeros) (student),
weights byte-identical to `models/ner/`. Steps 1 to 3 are done; steps 4 and 5
(load the app from the Hugging Face id, re-run the evaluation) are still open.

## What we would publish

| Model | Built from | Ownership |
|---|---|---|
| `teacher` (run 1) | `yashpwr/resume-ner-bert` fine-tuned on 2,310 of our resumes | Our model, a fine-tune of theirs: credit yashpwr |
| `student` (run 1) | `distilbert/distilbert-base-cased`, distilled from our teacher | Our model; all resume knowledge comes from our data and teacher |

Both are in `gs://smart-resume-analyzer-a7x2-data/runs/`. Scores (RESULTS.md,
corrected key): teacher 84 % DataTurks / 90 % unseen LiveCareer; student
81 % / 90 %; the app's current model 76 % / 64 %.

Recommendation: publish the teacher and use it in the app; the student is
optional, as a smaller version for other users.

## Licence obligations (Apache-2.0, both base models)

- Ship the Apache-2.0 `LICENSE` file.
- Say in the model card that it is fine-tuned from `yashpwr/resume-ner-bert`
  (or distilled onto `distilbert-base-cased`).
- No permission needed; it can be named and published as ours.

Project decision (DATASETS.md, 2026-10-10): non-commercial use. The model card
says "research and non-commercial use" and lists the training sources.

## Rules

1. Upload only the model files (weights, config, tokenizer). Never the
   training or test resumes: they contain personal details.
2. Model card: what it is (BERT token classifier for resume fields), training
   data (LiveCareer resumes with Gemini labels, 100 DataTurks resumes), the
   scores above, intended use, known weaknesses (company names on Indian-style
   resumes; test sets used three times, see RESULTS.md caveats).
3. Public is better for the portfolio and needs no token. Private needs an
   `HF_TOKEN` read token in `ml-service/.env` (a Hugging Face token, not a
   Google key).

## Steps

1. Owner creates a Hugging Face account and runs `hf auth login`.
2. Copy the teacher from the bucket; write the model card, `LICENSE` and
   attribution.
3. Upload from the laptop or Cloud Shell (a few hundred MB, no compute).
4. Point the app at it: `ner_model_name` and `ner_model_revision` in
   `ml-service/app/config.py` and `.env.example`, `engine_version` to 0.5.0,
   update the tests.
5. Re-run `evaluate_model.py` against the downloaded copy; it must reproduce
   84 % / 90 %.

## Decisions still needed from the owner

- Hugging Face username.
- Public or private (recommended: public).
- Model name (suggestion: `resume-ner-bert-careeros`).
- Teacher only, or teacher and student.
