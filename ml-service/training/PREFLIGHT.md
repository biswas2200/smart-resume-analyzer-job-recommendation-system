# Pre-flight checklist: GCP data work

Checks to pass before each stage of [gcp-setup.md](gcp-setup.md). The aim is to
catch a mistake before it costs money, loses labels already paid for, or exposes
resume data. `gcp/preflight.sh STAGE` runs the checks marked "auto". It only
reads: it creates, changes and deletes nothing and calls no paid API. Stop at
the first FAIL and fix it before going on.

```bash
cd ml-service
training/gcp/preflight.sh setup     # then data, vm, label, after
```

Each automated check was also tested to fail when it should: a one-word prompt
edit fails 4.3, and one altered file hash fails 4.1.

## 1. Before creating anything (`setup`)

| # | Check | Pass when | How | Why |
|---|---|---|---|---|
| 1.1 | gcloud account and project | an active account; project `smart-resume-analyzer-a7x2` | auto | Every command lands in this project |
| 1.2 | Application Default Credentials | a token is issued; its quota project is this project | auto | Gemini and Storage calls authenticate with no key file |
| 1.3 | Billing | enabled | auto | Vertex AI and Compute Engine need it |
| 1.4 | Budget alert | a budget exists on the billing account | auto | An email at 50, 90 and 100 % of ₹2,200 (about $25) of gross spend (credits excluded). It warns; it does not stop anything |
| 1.5 | APIs | Compute Engine, Cloud Storage and Vertex AI enabled | auto | |
| 1.6 | Code committed | no uncommitted `.py` or `.sh` change under `ml-service/` | auto | The VM runs a known commit, so every label can be traced to the code that made it |

## 2. Data in the bucket (`data`)

| # | Check | Pass when | How | Why |
|---|---|---|---|---|
| 2.1 | Bucket region | `ASIA-SOUTH1` | auto | Same region as the VM: no transfer charges |
| 2.2 | Bucket private | uniform bucket-level access on; public access prevention enforced | auto | The resumes contain real names, phone numbers and email addresses |
| 2.3 | Soft delete | deleted or overwritten files kept 7 days or more | auto | A wrong delete or overwrite can be undone |
| 2.4 | Raw copy complete | an rsync dry run from `datasets/` would copy nothing | auto | The VM works on exactly the laptop's files |
| 2.5 | Paid labels uploaded | the bucket's label file starts with the laptop's 10 labelled resumes | auto | The VM skips them instead of paying twice |

## 3. VM ready (`vm`)

| # | Check | Pass when | How | Why |
|---|---|---|---|---|
| 3.1 | Service account | `data-prep` exists | auto | The VM's identity for ADC |
| 3.2 | Least privilege | its only project roles are `aiplatform.user` and `logging.logWriter`; `storage.objectAdmin` on this bucket only | auto | Code on the VM can call Gemini, write its report to Cloud Logging and use this bucket, nothing else |
| 3.3 | VM shape | running in `asia-south1-a`, as that service account, no GPU, not Spot | auto | Google can stop a Spot VM at any time, which would halt the unattended run. A standard VM costs a few cents more for the run |
| 3.4 | Same code | the VM's code fingerprint equals the laptop's committed `.py` and `.sh` files | auto | |
| 3.5 | Same Python | 3.12 in the VM's venv, as on the laptop | auto | HTML-to-text cleaning could differ between Python versions |

## 4. Before the full labelling run (`label`)

| # | Check | Pass when | How | Why |
|---|---|---|---|---|
| 4.1 | VM build = laptop build | every prepared file's SHA-256 matches the laptop's, and both have the same files | auto | Proves the cleaning gives the same result on GCP |
| 4.2 | Eval resumes left out | none of the 20 LiveCareer eval IDs in the pool, compared as `livecareer-<id>` because the eval file stores bare IDs; DataTurks 0111 to 0130 in `test` | auto | Never train on the resumes used to measure the model |
| 4.3 | Labelling logic unchanged | prompt, schema, filters and rules identical to commit `6f8d308`, where the 10-resume sample was measured (only the retry helper and docstrings may differ) | auto | The quality numbers in [LABELLING.md](data_prep/LABELLING.md) still apply. Otherwise bump `PROMPT_VERSION` and re-run the quality gate |
| 4.4 | Projected cost | dry-run estimate × the sample's actual/assumed ratio at most $12 (the cap) | by hand | The estimate alone runs high on purpose (it assumes a fixed answer length): measured cost on pool resumes has been 0.56 to 0.62 of it, so the pool's $13.70 estimate projects to about $8 |
| 4.5 | VM sample of 5 | at most $0.007 per resume on average (twice the laptop sample's $0.0035); `not_in_text` at most 1 % of answers; no error | by hand | The VM path works and costs what the laptop sample did |
| 4.6 | Budget | spent so far (about $2.04) plus the dry-run estimate at most $20 | by hand | The labelling budget |
| 4.7 | Unattended run | `vm.sh full`: cap $12; labels copied to the bucket every 5 minutes; restarts only after a crash that made progress, 5 at most; the VM powers off at the end | by design | Paid labels are never lost, a failure cannot repeat at a cost, and nothing runs after the job |
| 4.8 | Report email armed | the "Data work: labelling report" alert is enabled, its email channel is **verified**, and `report_on_finish.sh` is waiting on the VM | auto | The report reaches you by email with the laptop off. Google silently drops alert emails to an unverified channel: two test alerts never arrived until the channel was verified |

## 5. After the run (`after`)

| # | Check | Pass when | How | Why |
|---|---|---|---|---|
| 5.1 | Clean finish | `labelled/DONE` reports `exit=0` | auto | |
| 5.2 | Complete | the label file has one line per pool resume (2,461) | auto | |
| 5.3 | VM off | not running | auto | It keeps billing while it runs |
| 5.4 | Quality numbers | `not_in_text` near 0; `placeholder_dropped` present, which shows the filter is working; no validation error in `run.log` | by hand | |
| 5.5 | Spot check | 3 records by eye: references' titles, awards and job dates in the wrong field | by hand | |
| 5.6 | Spend recorded | the actual cost from `run.log` in LABELLING.md | by hand | |
