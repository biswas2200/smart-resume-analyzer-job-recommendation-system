# Labelling resumes with Gemini

How the unlabelled LiveCareer resumes get NER labels, what it costs, and the
checks that keep both the bill and the labels honest. Read this before any
labelling run; every number here was measured on 2026-10-07/08 with prompt v3.

**Use `gemini-3.5-flash-lite` with prompt v3** (the script's current prompt and
minimal thinking). It matched the best scores on both check sets, follows the
prompt far better than the 2.5 models (11 placeholders to filter where
2.5-flash produced 137), and the whole pool costs about $9, the same as
2.5-flash. Decided 2026-10-08.

## The short version

```bash
cd ml-service
export GOOGLE_CLOUD_PROJECT=smart-resume-analyzer-a7x2     # or put it in ml-service/.env
IN=../datasets/prepared/records/livecareer_unlabelled.jsonl
OUT=../datasets/labelled/gemini-3.5-flash-lite.v3.jsonl

# 1. Estimate (free, no API call)
python -m training.data_prep.gemini_label $IN --model gemini-3.5-flash-lite --out $OUT --dry-run
# 2. Small real sample, then compare "actual" with "assumed" in the output
python -m training.data_prep.gemini_label $IN --model gemini-3.5-flash-lite --out $OUT --limit 10 --max-usd 0.50
# 3. Quality check of the sample (see "Quality gates"), then the full run
python -m training.data_prep.gemini_label $IN --model gemini-3.5-flash-lite --out $OUT --max-usd 12
```

Re-running the same command continues where it stopped: resumes already in
`$OUT` are skipped, so nothing is paid for twice.

## Which model

Two check sets, both git-ignored under `datasets/eval-unseen/`:

- Tuning set: 20 hand-labelled LiveCareer resumes from 20 job fields
  (answer key adjudicated, see below). The prompt and the rules were improved
  on these, so scores here are optimistic. Precision, recall and F1 on job
  title, degree, institution and graduation year.
- Independent set: DataTurks test resumes 0111 to 0130 (`dataturks-check/`),
  a different style (Indian Indeed resumes, real names and employers), never
  used for tuning. Its human key is incomplete (27 job titles and 5
  graduation years in 20 resumes), so recall is the fair measure there.

Tuning set, macro F1 over the four fields:

| Model | v1 prompt | v2 prompt | v3 prompt + year rules |
|---|---|---|---|
| gemini-2.5-flash-lite | 89 % | 91 % | **98 %** |
| gemini-2.5-flash | 89 % | 91 % | **96 %** |
| gemini-2.5-pro | 93 % | not run | not run |
| gemini-3.5-flash-lite | not run | not run | **97 %** |
| gemini-3.5-flash | not run | not run | **98 %** |

Independent set, recall against the human labels with v3:

| Field | 2.5-flash-lite | 2.5-flash | 3.5-flash-lite | 3.5-flash |
|---|---|---|---|---|
| Name | 90 % | 100 % | 100 % | 100 % |
| Job title | 85 % | 89 % | 93 % | 89 % |
| Employer | 100 % | 96 % | 100 % | 100 % |
| Degree | 89 % | 95 % | 95 % | 100 % |
| Institution | 89 % | 100 % | 100 % | 100 % |
| Graduation year | 100 % | 100 % | 100 % | 100 % |

All four are within the noise of a 20-resume test on the tuning set. On the
independent set 3.5-flash-lite has the highest minimum recall (93 %), and the
3.5 models needed the fewest corrections from the placeholder filter and the
year rule. 3.5-flash is as accurate but costs about $34 for the pool. A by-eye check of the 17 graduation years flash-lite
gave on the independent set found 16 correct (one year came from a prose line
next to a degree). For comparison, the app's local NER parser scored 64 % on
the tuning set's fields, measured against the key before adjudication.

## What it costs

Vertex AI list prices used by the script (`PRICES` in `gemini_label.py`):

| Model | Input / output, USD per 1M tokens | Thinking | Measured per resume | 2,461 LiveCareer resumes |
|---|---|---|---|---|
| gemini-2.5-flash-lite | 0.10 / 0.40 | off | $0.0010 | about $2.40 |
| gemini-2.5-flash | 0.30 / 2.50 | off | $0.0036 | about $8.90 |
| gemini-2.5-pro | 1.25 / 10.00 | on (cannot be turned off) | $0.049 (range $0.015 to $0.124) | about $120 |
| gemini-3.5-flash-lite | 0.30 / 2.50 | MINIMAL (0 thinking tokens measured) | $0.0037 | about $9.10 |
| gemini-3.5-flash | 1.50 / 9.00 | MINIMAL (0 thinking tokens measured) | $0.0139 | about $34 |

The 3.5 prices are from the Vertex AI pricing page (global endpoint, standard
tier, 2026-10-08): 3.5 is not cheaper than 2.5; 3.5-flash-lite costs what
2.5-flash costs.

Thinking tokens are billed at the output price, which is why pro costs so much
more: it thinks 800 to 6,900 tokens per resume before answering.

Estimates are deliberately rough (prompt = characters / 4, plus a fixed output
guess). Measured against them: flash-lite ran 20 to 75 % over (long skill
lists), flash 10 to 20 % under, pro 40 % under on average but up to 1.5x over
on the longest resume. The cap below absorbs that.

## The full pool run (2026-10-09)

Run on the GCP VM (`training/gcp/vm.sh full`, see ../gcp-setup.md §5),
gemini-3.5-flash-lite, prompt v3, cap $12.

| | Result |
|---|---|
| Resumes | all 2,461 pool resumes labelled (2,446 in this run, 15 from the samples); every record passed validation |
| Time | 2 h 55 min (13:11 to 16:07 IST), no restarts; 87 rate-limit (429) retries, all recovered |
| Cost | $7.18 actual against $13.67 estimated: $0.0029 per resume, 0.53 of the estimate |
| Labelling spend to date | about $9.24 of the $20 budget |
| Answers | 120,618; 252 not found in the text (0.21 %); 1,401 placeholders and 510 overlaps dropped |
| Graduation years | 2,995 dropped and 965 added by the year rule; 4,140 kept |
| Entities kept | 116,202: Skills 82,520, Designation 16,457, College Name 5,438, Degree 4,837, Graduation Year 4,140, Years of Experience 1,197, Companies worked at 1,128, Location 1,057, Name 189, Phone 70, Email Address 17 |

By-eye check: 3 random records were correct field by field. Of the 483
records with a degree or school but no graduation year, 427 state no year in
their education lines at all; the other 56 have the year on a certification
line, which the rule excludes on purpose. Known small defects to filter when
building BIO files: a few graduation years that are not years (2 × "Present",
2 × "May"). Names, employers and contact details are rare because LiveCareer
is anonymised; those labels come mainly from DataTurks.

Output: `gs://smart-resume-analyzer-a7x2-data/labelled/gemini-3.5-flash-lite.v3.jsonl`,
with `run.log` and `REPORT.json` next to it.

## Safety features in the script

| Feature | What it prevents |
|---|---|
| `--dry-run` | Spending anything before seeing the estimate |
| `--max-usd` (default $1) | Overspending: before each call the script checks spent + 2 x the call's estimate against the cap and stops cleanly if it would cross it |
| Skip already-labelled IDs | Paying twice after a crash, a 429 or a stopped run |
| Retry on 429 and 5xx | A rate-limit pause or a passing server fault killing a long run (waits 10, 20, 40 ... seconds); neither is billed |
| Answer schema with a label enum | Models inventing label names ("Skill", "Job Title"); pro did this 176 times before the schema |
| Exact-text alignment | Paraphrased or invented values becoming labels: an answer that is not verbatim in the resume is dropped and counted (`not_in_text`) |
| Placeholder filter | LiveCareer's anonymisation ("Company Name", "City", "State", "[Job Title]") being labelled; flash-lite labelled 184 of them in one run despite the prompt |
| Validation before writing | Broken spans reaching training files (same checks as `build.py`) |
| `prompt_version` and `model` in each record's `meta` | Mixing labels from different prompts without knowing |

## Quality gates (check after the sample, before the full run)

1. `not_in_text` stays near 0. A rising count means the model is paraphrasing.
2. `placeholder_dropped` is expected on LiveCareer; it means the filter is
   working, not that labels are wrong.
3. Label both check sets with the same model and prompt, then score them:
   ```bash
   E=../datasets/eval-unseen
   python -m training.data_prep.gemini_label $E/sample.jsonl --model gemini-3.5-flash-lite \
     --out $E/gemini/gemini-3.5-flash-lite.v3.jsonl --split test --max-usd 0.30
   python -m training.data_prep.gemini_label $E/dataturks-check/dataturks_test20.jsonl --model gemini-3.5-flash-lite \
     --out $E/dataturks-check/gemini-3.5-flash-lite.v3.jsonl --split test --max-usd 0.30
   python $E/compare_gemini.py gemini-3.5-flash-lite.v3
   python $E/dataturks-check/compare_dataturks.py gemini-3.5-flash-lite.v3
   ```
   About $0.11 together. Neither score may fall more than 5 points below the
   tables in "Which model". After any prompt or rule change, bump
   `PROMPT_VERSION` and re-run this gate before labelling the pool.
4. Spot-check 3 records by eye: print each entity with its label and look for
   references' titles, awards and job dates in the wrong fields.

The 20 eval resumes are excluded from the training pool by `build.py`; they
are labelled only to measure quality and never trained on.

## How the prompt and rules were improved

Each row is an error measured on the check sets and the fix that removed it:

| Error seen | Example | Rule added |
|---|---|---|
| References' titles as job titles | lines after "Anna Mwinga" | ignore the References section; never another person's title |
| Awards as job titles | "Group Leader", "Best Cashier" | never an award or honour |
| Template placeholder | "[Job Title]" | placeholder rule + filter |
| Group nouns | "employees" | never a word for other people |
| Majors, coursework, honours as degrees | "Criminal Justice", "Deans List" | never a major, coursework or honour |
| Unfinished certification as a degree | "Pursuing PMP certification" | never in progress |
| Job dates as graduation years (flash) | "05/2014 to 08/2014" | never a job, award or certification date |
| Years on their own line missed (flash-lite) | "2008" above the school | include a year just above or below a school or degree |
| Clients as employers (v3) | "Client: StateFarm" | an employer is never a client or customer |
| Job ranges, prose years and certification dates still labelled as graduation years (prompt alone did not stop it) | "04/2014 to 02/2016", "joined Accenture in 2006" | code rule `fix_graduation_years`: a graduation year must be on a degree or school line or the nearest non-empty line above or below; in an education range ("2016 to 2018") the end date counts |
| Rule first looked at the literal next line, so a blank line hid the year (found only on the independent set) | "Calicut University" / blank / "2016 to 2018" | neighbouring line = nearest non-empty line |

## The answer key was corrected too

About half of the "wrong" answers in the first comparison were correct values
missing from the hand labels (titles inside one long job entry, a skipped job,
lines that were cut when printing). Each was checked against the resume text
and added; the list is in `datasets/eval-unseen/ADJUDICATION.md` and the
original key is kept as `labels.before-adjudication.jsonl`. When a model and
the key disagree, check the resume before trusting either.

## Known limits

- 20 resumes is a small evaluation set: differences under about 5 points are
  noise.
- The prompt was tuned on the LiveCareer 20, so their score is optimistic;
  the DataTurks 20 are the honest check, and only on recall.
- The year rule can still take a year from a prose line that happens to sit
  next to a degree line (1 of 17 on the independent set).
- gemini-2.5-pro was only run with the v1 prompt; with v3 it might do better,
  but at about $120 for the pool it is outside the budget anyway.
- Skills are labelled one per skill, unlike DataTurks, which marks whole skill
  paragraphs. Do not mix the two styles in one training set without deciding
  how the model should tag skills.
- Names and employers are anonymised in LiveCareer, so those labels come only
  from DataTurks.
