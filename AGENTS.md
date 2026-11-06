# Project context for AI coding assistants

Read this before changing anything. `README.md` and each module's README hold
the details; this file holds the decisions and rules that aren't obvious
from the code.

## What Smart Resume Analyser and Job Recommendation System is

Smart Resume Analyser and Job Recommendation System is a resume analyser and job recommendation system. A user uploads a
resume (PDF or DOCX) and gets:

- the detected job domain (one of 23), an ATS score with fixes, a parsed profile
- matched catalogue roles with skill gaps and an explanation
- live job openings in Bengaluru ranked against the resume, saved jobs, and a
  company watchlist
- a match against a pasted job description

Version: **0.6.0** (ML engine 0.5.5). Every release stays 0.x until a
production-ready beta; don't call anything 1.0.

## Architecture

| Module | Stack | Port |
|---|---|---|
| `ml-service/` | Python 3.12, FastAPI, PyTorch/transformers, sentence-transformers | 8000 |
| `backend/` | Java 21, Spring Boot 3.3, Spring Security (JWT), JPA, Flyway (V1-V9), PostgreSQL, MinIO | 8080 |
| `frontend/` | HTML, one CSS file, vanilla JS ES modules, no build step | 4200 |
| `deploy/` | Docker Compose + Caddy for a single VM | |
| `docs/` | MkDocs site: SRS, HLD/LLD, DFD, schema, UML | |

The browser only talks to the backend. The backend calls the ML service over
HTTP (`POST /analyze-file`, `/rank-jobs`, `/extract-job-skills`,
`/market-demand`, `/match-jd`, `PUT /weights-snapshot`).

### Resume parsing: the local NER model

Engineering & Technology resumes are parsed fully offline by our own NER
model, with no API call:

- Model: our fine-tune of `yashpwr/resume-ner-bert` (the "teacher", about
  412 MB), loaded from `ml-service/models/ner/teacher-run1` and pinned by the
  SHA-256 of its weights (`NER_MODEL_REVISION`). A smaller distilled
  "student" (about 250 MB) is the alternative.
- Code: `app/services/local_ner_parser.py` (NER), `sectioner.py` (splits the
  resume into sections), `dictionary_skills.py` and `normalizer.py` (skills),
  `gcs_download.py` (fetches the weights at start-up when the folder is
  missing).
- The weights are not in git (`ml-service/models/` is ignored, too large).
  Unzip the model archive into `ml-service/models/ner/`, or let the service
  download it from `NER_MODEL_GCS_URI` with Google ADC. It refuses to start
  if the weights don't match the pin.
- Training and evaluation: `ml-service/training/` (`RESULTS.md` has the
  numbers). Training ran on a GCP GPU VM, never on a laptop.
- The other 22 domains are read by the same model and parser too: jobs, degrees and
  colleges from the NER model, skills from the all-domain dictionary and the Skills
  section (the model was trained on IT resumes, so its skill spans are used for
  engineering only). Gemini (Vertex AI) only writes the coaching narrative, with a
  template fallback, so no upload needs Google credentials. A domain can be switched to
  LLM extraction by setting its `engine` to `llm` in `domains.json`. Matching and
  scoring stay deterministic for every domain.

### Matching, jobs and the EMA loop

- Role matching: MiniLM (`all-MiniLM-L6-v2`) embeddings plus skill coverage
  against curated role catalogues in `ml-service/app/data/`.
- Job ranking (`services/job_rank.py`):
  `score = 0.45·coverage·evidence + 0.30·similarity + 0.25·role_fit`, with
  `evidence = min(1, job skills / 5)`; `0.5·role_fit` when a job's skills
  can't be read. Deterministic, no LLM.
- Job sources: Wikidata (companies with HQ in Bengaluru) and the Bangalore
  Startup Map's public pages (used with the creator's permission) give the
  company list. Jobs come from each company's public Lever, Greenhouse and
  Ashby feeds. Every job links to the original posting.
- Skill weights follow an EMA: `new = α·signal + (1−α)·old`, α = 0.3. Signals
  come from user feedback and from daily job-market demand
  (`market_demand.py`; signal = 0.5 + 0.5·share/maxShare).
- One version of the product: there are no tiers. Every account gets five role matches, the
  AI-written narrative, JD match, unlimited analyses and history. `LLM_DAILY_BUDGET_USD`
  (off by default) is the operator's cost brake.

## How to run and test

```bash
# ML service
cd ml-service && python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt && cp .env.example .env
python -m pytest -q            # the NER model and LLM calls are mocked
uvicorn app.main:app --reload

# Backend (Postgres + MinIO from the root docker-compose.yml)
docker compose up -d
cd backend && APP_ADMIN_EMAILS=you@example.com mvn spring-boot:run
mvn -B -q test

# Frontend
python3 -m http.server 4200 --directory frontend/src
cd frontend && npm test        # node --test, no dependencies
```

`.github/workflows/ci.yml` runs all three test suites on every PR. Keep them
green: backend and frontend tests.

## Rules

- **Google access is Application Default Credentials only**
  (`gcloud auth application-default login` + `GOOGLE_CLOUD_PROJECT`). Never
  add a Google API key, key field or key env var.
- **No scraping** of LinkedIn, Naukri or Indeed, and no calls to the
  Bangalore Startup Map's `/api/` (its robots.txt disallows it). Only public
  pages and official public job feeds.
- **Measure LLM cost before any full run**: `scripts/llm_cost_check.py
  --dry-run`, then a small real sample, and compare assumed vs actual before
  running a workflow over many resumes. The default model is
  `gemini-2.5-flash-lite` with thinking off (about $0.00035 per analysis).
- **Heavy work runs on GCP** (training, labelling, dataset cleaning); the
  laptop is for editing and small checks.
- Datasets: the training data is licensed for non-commercial use; trained
  models may ship. See `docs/datasets.md`. Datasets are not in git.
- Never commit secrets: `deploy/.env` stays on the server, `.env` files are
  ignored.
- Commit and push only when asked. Work on a branch and open a PR to
  `master`.
- Match the surrounding code: plain names, short comments that say why,
  tests next to every change.

## Parsing notes

The NER model tags spans well but entity order is a poor guide to which
institution, year or company belongs to which record. `local_ner_parser.py`
therefore rebuilds education from the Education section's own lines
(`_assemble_education`: each degree line owns a block, and takes the first
institution and latest year inside it, whichever order the resume uses) and
repairs jobs from their lines (`_repair_experience`: cut-off titles and
companies, jobs the model skipped, durations on the job's own line). The
model's entities are the fallback when no degree is written on a line.
Layout regressions live in `tests/test_local_ner_parser_layouts.py`; add the
failing resume there first. `scripts/evaluate_resume_categories.py` measures the
parser and the domain classifier on real resumes from every field (the LiveCareer
set in `datasets/`); keep its job/degree/college rates from dropping. Still open:
quality outside engineering is lower than inside it (company names, a college with
a field name stuck to it, noisy skills from long prose), and the F1 in
`training/RESULTS.md` has not been re-run since these passes were added.
