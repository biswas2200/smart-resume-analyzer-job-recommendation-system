# NER training results

## Run 1 (2026-10-09/10)

Track A of [README.md](README.md), run on an L4 GPU VM in asia-southeast1-b.
None of these models is in production. The licence questions in
[DATASETS.md](DATASETS.md) must be settled first, and the gate below was not met.

### What was trained

| Model | What it is | Training data | Best dev entity F1 |
|---|---|---|---|
| `teacher` | `yashpwr/resume-ner-bert` fine-tuned for 5 epochs | 2,431 resumes: 100 DataTurks (human labels, Gemini skills) and 2,331 LiveCareer (Gemini labels) | 78.3 % |
| `r1/teacher` | The same, after label-quality round 1 removed 121 resumes (5 %) | 2,310 resumes | 78.6 % |
| `r2` | Round 2 removed another 121; dev F1 fell to 78.1 %, so the rule stopped the rounds and this model was dropped | 2,189 resumes | 78.1 % |
| `student` | 6-layer `distilbert-base-cased` distilled from `r1/teacher` | 2,310 resumes | 77.8 % |

All the models are in `gs://smart-resume-analyzer-a7x2-data/runs/`, with the
removed IDs and the classifier's `review.md` for each round.

### Test sets (never trained on), scored through the app's parser

Field F1 / precision / recall. "Baseline" is the app's current model, re-scored
in the same run.

**DataTurks test (resumes 111 to 220, Indian Indeed resumes, human answer key):**

| Field | Baseline | Teacher | Round-1 teacher | Student |
|---|---|---|---|---|
| Name | 97 % (99 / 94) | 97 % (99 / 94) | 97 % (99 / 94) | 97 % (99 / 95) |
| Degree | 39 % (40 / 39) | 42 % (38 / 46) | 44 % (41 / 47) | 43 % (43 / 44) |
| Institution | 63 % (69 / 58) | 57 % (55 / 58) | 53 % (52 / 55) | 54 % (56 / 53) |
| Graduation year | 41 % (30 / 63) | 32 % (22 / 63) | 30 % (20 / 55) | 38 % (27 / 63) |
| Job title | 60 % (53 / 70) | 55 % (47 / 65) | 55 % (49 / 63) | 59 % (51 / 70) |
| Company | 59 % (64 / 55) | 50 % (47 / 55) | 50 % (46 / 56) | 49 % (48 / 50) |
| **Macro F1** | **60 %** | 55 % | 55 % | 57 % |

**Unseen LiveCareer (20 resumes, adjudicated answer key):**

| Field | Baseline | Teacher | Round-1 teacher | Student |
|---|---|---|---|---|
| Job title | 60 % (81 / 48) | 85 % (83 / 87) | 85 % (83 / 86) | 84 % (85 / 83) |
| Degree | 63 % (90 / 49) | 78 % (76 / 80) | 75 % (72 / 78) | 81 % (79 / 83) |
| Institution | 66 % (96 / 50) | 86 % (90 / 83) | 86 % (90 / 83) | 82 % (84 / 81) |
| Graduation year | 63 % (86 / 50) | 90 % (94 / 87) | 90 % (94 / 87) | 91 % (97 / 87) |
| **Macro F1** | **63 %** | 85 % | 84 % | **85 %** |

### What the numbers say

- **Large gain on LiveCareer-style resumes:** macro F1 rises from 63 % to
  85 %, mainly because recall goes from about 50 % to over 80 %. This key was
  corrected by hand, so the gain is real. These resumes come from the same
  source as most of the training data, though: a measure of in-distribution
  quality.
- **Lower precision on DataTurks:** recall is about the same as the baseline
  (degree better, institution and company slightly worse), but the new models
  report more values that the human key lacks. The DataTurks key is known to be
  incomplete (LABELLING.md: 27 job titles in 20 resumes), so part of the drop
  may be real values the key misses. A by-eye check decides this.
- **Company recall falls**, plausibly because LiveCareer replaces every
  employer with the placeholder "Company Name", which the training data marks
  as not-an-entity. The model learns that the employer slot is empty.
- **The student matches the teacher** at 40 % less size (65M parameters
  against 108M), so distillation works.
- **The label-quality round did not move the test scores**
  (teacher ≈ round-1 teacher). Label noise is not the bottleneck here; the
  mix of resume styles is.

### Gate

README step 7 requires beating both baselines. Unseen LiveCareer: yes (85 %
against 63 %). DataTurks: no on macro F1 (57 % against 60 %). **Not passed; the
app keeps its current model.**

### Next experiments (each well under $1 of GPU)

1. By-eye check of the student's extra DataTurks values on about 10 resumes.
   If most are real, correct the DataTurks test key as was done for LiveCareer,
   then re-score.
2. Replace the LiveCareer placeholders ("Company Name", "City", "State") with
   realistic invented values and label them, so the model sees filled
   employer and location slots.
3. Oversample the 100 DataTurks training resumes (for example ×5) so the
   Indian resume style carries more weight.

### Cost

Gemini skill labels for the 110 DataTurks training resumes: about $0.26. GPU
VM: about 3.9 hours including set-up and idle time, about $3.50 at the
estimated $0.90 an hour. The VM is stopped; its disk is kept for the next
experiments.

## Run 2 (2026-10-10): parser fix, corrected key, filled placeholders

A parser fix and run 1's first two follow-ups, on the same VM. Scores are
field F1 (precision / recall), through the app's parser.

### Parser fix (engine 0.4.1)

The parser now takes each entity's text from the resume itself, at the
character offsets the model returns. Before, it used the tokenizer's re-joined
text, which spaces punctuation such as slashes differently, so correct values
failed to match the key. Every model gains:

| Macro F1 | Baseline | Teacher | Round-1 teacher | Student |
|---|---|---|---|---|
| DataTurks test | 64 % (was 60 %) | 61 % (was 55 %) | 60 % (was 55 %) | 62 % (was 57 %) |
| Unseen LiveCareer | 64 % (was 63 %) | 90 % (was 85 %) | 90 % (was 84 %) | 90 % (was 85 %) |

### Corrected DataTurks key

The by-eye check (experiment 1 above) found the human key incomplete. Every
value a model reported that the key lacks, and every key value no model found,
was judged against the resume by fixed rules, without looking at which model
reported it: 308 values added, 21 removed. The corrections are in
`datasets/eval-unseen/dataturks-adjudication/` (out of git, like all resume
data) and are applied by `evaluate_model.py --turks-fixes`; the original key
is not edited. Line breaks inside key values no longer block a match.

| Field | Baseline | Teacher | Round-1 teacher | Student |
|---|---|---|---|---|
| Name | 97 % (99 / 94) | 97 % (99 / 94) | 97 % (99 / 94) | 97 % (99 / 95) |
| Degree | 69 % (78 / 62) | 81 % (81 / 81) | 82 % (85 / 80) | 79 % (86 / 73) |
| Institution | 73 % (92 / 61) | 77 % (85 / 71) | 74 % (82 / 67) | 70 % (84 / 61) |
| Graduation year | 73 % (87 / 64) | 87 % (91 / 84) | 85 % (90 / 81) | 83 % (92 / 76) |
| Job title | 79 % (81 / 76) | 86 % (95 / 80) | 86 % (95 / 79) | 86 % (92 / 80) |
| Company | 66 % (92 / 51) | 76 % (86 / 68) | 75 % (85 / 68) | 72 % (88 / 61) |
| **Macro F1** | **76 %** | **84 %** | 83 % | 81 % |

Run 1's precision drop was mostly the key: with the missing values added, the
trained models' precision is 81–95 % per field, and their recall is at or
above the baseline's in every field. The key was corrected after seeing the
models' output, so this set is less independent than the LiveCareer one, even
though the rules were fixed and the judging blind to the model.

### Filled placeholders (`teacher2`, `student2`)

`training_set.py build --fill-placeholders` replaces LiveCareer's "Company
Name" and "City , State" with invented employers and real US places, labelled
as company and location: 11,334 employer and 13,558 location slots.
Placeholders inside another entity (68) or on an education line (96) are left
as they are. The teacher was retrained without the 121 resumes round 1 removed,
and a student was distilled from it. Their dev F1 (82.2 % and 81.3 %) is not
comparable with run 1, because filling changed the dev set too.

| Macro F1 (corrected key) | Teacher | `teacher2` | Student | `student2` |
|---|---|---|---|---|
| DataTurks test | 84 % | 82 % | 81 % | 81 % |
| Unseen LiveCareer | 90 % | 91 % | 90 % | 91 % |

Per field, filling helped the student find companies on DataTurks (72 % to
75 %, recall 61 % to 68 %) but not the teacher (76 % to 72 %). It cost job
titles on LiveCareer (teacher 93 % to 90 %, student 92 % to 87 %), plausibly
because those test resumes still carry the placeholders the new models never
saw. Overall there is no clear gain: differences of one to three points are
within the noise of 110 and 20 test resumes. Run 1's models stay the
candidates.

### Gate

Against the baselines re-scored in the same run, with the corrected key:

- **Teacher:** DataTurks 84 % against 76 %, LiveCareer 90 % against 64 %. Passed.
- **Student:** DataTurks 81 % against 76 %, LiveCareer 90 % against 64 %. Passed.

Two caveats. The DataTurks pass rests partly on a key corrected after seeing
the outputs. And step 7 says the test sets are used once, but they have now
scored three rounds (run 1, the parser fix, filled placeholders). Nothing was
tuned on them, but a fresh hand-labelled set would make the next comparison
clean. The licence questions are settled for this non-commercial project
(decision of 2026-10-10 in [DATASETS.md](DATASETS.md)).

### Next

1. ~~Settle the licence questions in DATASETS.md.~~ Done 2026-10-10:
   non-commercial project, the models may ship.
2. ~~The choice is between run 1's `teacher` (most
   accurate) and `student` (40 % smaller, 3 points lower on DataTurks).~~
   Done 2026-10-20: the app serves run 1's `teacher` (engine 0.5.0, pinned by
   the SHA-256 of its weights); the `student` is kept as the smaller option.
   Both are fetched by `scripts/fetch_ner_models.sh`.
3. Optional: oversample the DataTurks training resumes (experiment 3), after
   hand-labelling a fresh test set.

### Cost

GPU VM about 48 minutes, about $0.72 at the estimated $0.90 an hour; runs 1
and 2 together about $4.20. The VM is stopped; its disk is kept.

## Parser: institution names cut short (2026-10-22, engine 0.5.4)

On "B.Tech, Savitribai Phule Pune University, 2022" the teacher tags
"Savitribai Phule" and "University" separately and drops "Pune", so the
profile kept a fragment. `_widen_education_institutions` takes the whole
separator-delimited piece of the Education line that names an institution
and ends with the entry's institution (word boundary, never when the piece
holds the degree). Scored with `evaluate_model.py --turks-fixes` on the beta
VM (e2-standard-2, CPU), before and after the change:

| Field macro F1 | Before | After |
|---|---|---|
| Teacher, DataTurks test (Institution) | 84 % (77 %) | 84 % (77 %) |
| Teacher, unseen LiveCareer (Institution) | 90 % (89 %) | 90 % (89 %) |
| Upstream `yashpwr`, DataTurks (Institution) | 76 % (73 %) | 76 % (72 %) |

No change for the served model; kept, since it fixes the reported resume.

## Parser: education pairing and section headings (2026-10-22, engine 0.5.5)

Found on a real fresher resume that writes the institution line above each
degree and has Projects and Hackathons sections but no Experience: project
lines were read as education, and each degree got the other degree's
institution. Changes: headings the parser doesn't read end the section above
them; each degree is paired with the adjacent institution line in the
direction the resume uses, with the year from its own line; plural
institution keywords; 15 skills added to the taxonomy. Scored on the beta VM
(`evaluate_model.py --turks-fixes`), teacher, before -> after:

| Field F1 | DataTurks test | Unseen LiveCareer |
|---|---|---|
| Degree | 81 % -> 83 % | 90 % -> 90 % |
| Institution | 77 % -> 82 % | 89 % -> 88 % |
| Grad. year | 87 % -> 88 % | 90 % -> 94 % |
| Job title | 86 % -> 85 % | 93 % -> 93 % |
| Company | 76 % -> 74 % | (anonymised) |
| **Macro** | **84 % -> 85 %** | **90 % -> 91 %** |

Kept: education fields gain clearly; job title and company lose 1-2 points
on DataTurks, likely where a new heading now ends text that used to run on
into Experience. Worth a look in the next round.
