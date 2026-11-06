# GCP setup for data preparation and labelling

How the datasets move into Google Cloud and how the data work runs there. The
laptop only runs `gcloud` commands and the upload. Cleaning, preparation and
labelling run on a VM. Authentication is Application Default Credentials
throughout: your gcloud login on the laptop, the VM's service account on the
VM. No key file is created at any step. Training on a GPU comes later
([README.md](README.md) §2).

Before each stage, run its checks from [PREFLIGHT.md](PREFLIGHT.md), from
`ml-service/`: `training/gcp/preflight.sh setup|data|vm|label|after`.

Written against Google Cloud SDK 588. Commands run on the laptop unless a
step says "on the VM".

## 0. Values used below

| Name | Value |
|---|---|
| Project | `smart-resume-analyzer-a7x2` |
| Region / zone | `asia-south1` (Mumbai) / `asia-south1-a` |
| Bucket | `gs://smart-resume-analyzer-a7x2-data` |
| VM | `data-prep-vm` (e2-small, Ubuntu 24.04), service account `data-prep` |
| BigQuery dataset | `resume_data` (same region as the bucket) |

Keep everything in one region: BigQuery can only load from a bucket in its
own location, and traffic inside a region is free.

```bash
export PROJECT=smart-resume-analyzer-a7x2
export REGION=asia-south1
export ZONE=asia-south1-a
export BUCKET=gs://smart-resume-analyzer-a7x2-data
export SA=data-prep@$PROJECT.iam.gserviceaccount.com
gcloud config set project $PROJECT
```

The scripts in `training/gcp/` use the same values (`common.sh`).

## 1. One-time setup

```bash
gcloud services enable compute.googleapis.com billingbudgets.googleapis.com
```

Cloud Storage, Vertex AI and BigQuery are already enabled.

### Budget alert

An email when gross spend reaches 50 %, 90 % and 100 % of ₹2,200 (about $25)
in a month. Credits are excluded, so the alert tracks real usage even while a
free-trial credit pays the bill. It only warns; it stops nothing. The amount
must be in the billing account's currency, INR for this account; `25USD` is
rejected with `INVALID_ARGUMENT`.

```bash
ACCOUNT=$(gcloud billing projects describe $PROJECT --format="value(billingAccountName)")
gcloud billing budgets create --billing-account=${ACCOUNT#billingAccounts/} \
  --display-name="resume-analyzer data work" --budget-amount=2200INR \
  --filter-projects=projects/$PROJECT --credit-types-treatment=exclude-all-credits \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

### Bucket

Private, with public access blocked, because the datasets contain real
resumes with names and email addresses. Soft delete is on by default: a
deleted or overwritten file can be restored for 7 days.

```bash
gcloud storage buckets create $BUCKET --location=$REGION \
  --uniform-bucket-level-access --public-access-prevention
```

| Prefix | Holds |
|---|---|
| `raw/` | The laptop's `datasets/` folder, file for file, without build outputs |
| `code/` | The committed `ml-service` code the VM runs, and its `VERSION` |
| `prepared/` | The VM's `training/data_prep` build, with `SHA256SUMS` |
| `labelled/` | Gemini labels, `run.log`, and `DONE` when the full run ends |
| `training/` | BIO files the training job reads (later) |

## 2. Upload the datasets from the laptop

One rsync copies the whole `datasets/` folder (about 6.6 GB, 2,900 files),
including the large LinkedIn posting sets, so nothing needs downloading on the
VM. Look at the dry run first.

```bash
cd ~/BiswasPub/smart-resume-analyzer-job-recommendation-system
EXCLUDE='^(prepared|labelled)/.*|.*__pycache__/.*|.*\.~lock\..*'
gcloud storage rsync --recursive --dry-run --exclude="$EXCLUDE" datasets $BUCKET/raw | tail
gcloud storage rsync --recursive --exclude="$EXCLUDE" datasets $BUCKET/raw
gcloud storage cp datasets/labelled/gemini-3.5-flash-lite.v3.jsonl $BUCKET/labelled/
```

- The exclusions are build outputs (the VM rebuilds `prepared/`; labels have
  their own prefix), Python caches and LibreOffice lock files.
- The last line uploads the 10 resumes already labelled on the laptop, so the
  VM skips them rather than paying for them again.
- Each file is checked against its hash on upload, and running the rsync again
  copies only what changed.

Folder names follow the laptop's: `archive` holds the LiveCareer resumes,
`archive (1)` DataTurks, and `archive (3)` and `archive (4)` the two LinkedIn
posting sets ([docs/datasets.md](../../docs/datasets.md)).

## 3. A VM for the resume work

### Service account

The VM acts as this account, so code on it gets Google credentials
automatically (ADC). No key file is created.

```bash
gcloud iam service-accounts create data-prep --display-name="Data prep VM"
gcloud storage buckets add-iam-policy-binding $BUCKET \
  --member=serviceAccount:$SA --role=roles/storage.objectAdmin
gcloud projects add-iam-policy-binding $PROJECT \
  --member=serviceAccount:$SA --role=roles/aiplatform.user --condition=None
gcloud projects add-iam-policy-binding $PROJECT \
  --member=serviceAccount:$SA --role=roles/logging.logWriter --condition=None
```

`roles/storage.objectAdmin` on the bucket lets it read and write this bucket
only; `roles/aiplatform.user` lets it call Gemini on Vertex AI;
`roles/logging.logWriter` lets it write the end-of-run report (§5).

### Create the VM

```bash
gcloud compute instances create data-prep-vm --zone=$ZONE \
  --machine-type=e2-small --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB --service-account=$SA --scopes=cloud-platform \
  --metadata=enable-oslogin=TRUE
```

- A standard VM rather than Spot. The labelling run takes about 3 hours
  unattended, and Google can stop a Spot VM at any time, which leaves the run
  halted until someone restarts it. For an e2-small the difference is a few
  cents.
- e2-small (2 shared vCPUs, 2 GB) is enough: the build needs under 60 MB, and
  labelling waits on the network. For heavier work, stop the VM, change its
  machine type with `gcloud compute instances set-machine-type`, and start it
  again.
- Ubuntu 24.04 ships Python 3.12, the laptop's version, so the text cleaning
  gives byte-identical output (pre-flight check 4.1 proves it).
- OS Login: `gcloud compute ssh` signs in with your Google account, and no
  SSH keys go into the project's metadata.

### Put the code on the VM

The VM runs committed code only: `push_code.sh` uploads `git archive` of
`ml-service` with a `VERSION` file (commit and code fingerprint), unpacks it on
the VM, and refuses to run while a `.py` or `.sh` file has uncommitted changes.
The first time, also create the Python environment.

```bash
cd ml-service
training/gcp/push_code.sh
gcloud compute ssh data-prep-vm --zone=$ZONE --command="bash ~/ml-service/training/gcp/vm.sh setup"
```

## 4. Prepare the resume data (on the VM)

```bash
gcloud compute ssh data-prep-vm --zone=$ZONE --command="bash ~/ml-service/training/gcp/vm.sh test && bash ~/ml-service/training/gcp/vm.sh build"
training/gcp/preflight.sh label
```

`vm.sh build` downloads only what the build reads, runs `training.data_prep.build`,
writes a SHA-256 for every output file and copies the result to `prepared/`.
The pre-flight then compares those hashes with the laptop's build. What the
build fixes and how to read its report: [data_prep/README.md](data_prep/README.md).

## 5. Gemini labelling with `gemini-3.5-flash-lite` (on the VM)

The unlabelled resumes are labelled by `gemini-3.5-flash-lite` with prompt v3,
the model chosen after measuring quality and cost on two check sets
([data_prep/LABELLING.md](data_prep/LABELLING.md)). The app's own Gemini
calls (extraction and coaching) are unaffected and stay on
`gemini-2.5-flash-lite`.

The cost rule, with the labeller's own checks:

```bash
V="bash ~/ml-service/training/gcp/vm.sh"
gcloud compute ssh data-prep-vm --zone=$ZONE --command="$V dry-run"    # estimate, no API call
gcloud compute ssh data-prep-vm --zone=$ZONE --command="$V sample 5"   # compare actual with assumed
gcloud compute ssh data-prep-vm --zone=$ZONE \
  --command="nohup setsid $V full > ~/full.out 2>&1 < /dev/null &"     # about 3 hours, unattended
```

`vm.sh full` labels the rest with `--max-usd 12` (about $9 for the 2,461-resume
pool). While it runs:

- It copies the labels and `run.log` to `$BUCKET/labelled/` every 5 minutes.
- After a crash that made progress it restarts, at most 5 times. Finished
  resumes are skipped, so a restart re-pays for at most the one resume that
  was in flight.
- At the end it writes `labelled/DONE` and powers the VM off.

### The report by email, with the laptop off

When the run ends, `report_on_finish.sh` (started on the VM next to the run)
writes a short report to Cloud Logging, and a Cloud Monitoring alert emails it
to you. It needs about 10 of the 60 seconds before the VM powers off. A second
alert emails when the VM stops, as a backstop in case no report comes. Your
address goes only into the alert's email channel, never into the repository.
The channel must be verified: Google accepts an unverified email channel but
silently drops every alert sent to it, which is why the script asks for the
code from the verification email. Both alerts email only when an incident
opens, not again when it closes.

```bash
training/gcp/setup_alerts.sh you@example.com             # emails a verification code, then stops
training/gcp/setup_alerts.sh you@example.com G-123456    # verifies the channel, creates the alerts
gcloud compute scp training/gcp/report_on_finish.sh data-prep-vm:~/ --zone=$ZONE
gcloud compute ssh data-prep-vm --zone=$ZONE \
  --command="nohup setsid bash ~/report_on_finish.sh > ~/report.out 2>&1 < /dev/null &"
```

Try it first: `bash ~/report_on_finish.sh --dry-run` on the VM prints the
report for the run so far, and writing one test entry to the `labelling-report`
log from the laptop (`gcloud logging write labelling-report '{"headline": "TEST"}'
--payload-type=json`) should produce the email within a few minutes. The
report also lands in `$BUCKET/labelled/REPORT.json`.

Progress from the laptop:

```bash
gcloud storage cat $BUCKET/labelled/run.log | tail -3
gcloud storage cat $BUCKET/labelled/DONE          # exists once the run has ended
```

## 6. Stop paying when done

The VM powers itself off after `vm.sh full`. A stopped VM costs only its 20 GB
disk, under $1 a month. Delete it when the data work is finished; the bucket
keeps every result.

```bash
training/gcp/preflight.sh after
gcloud compute instances delete data-prep-vm --zone=$ZONE   # when finished
```

## 7. Clean the job postings in BigQuery

Done 2026-10-10 for the 1.3M LinkedIn set (`archive (4)`). Everything runs in
BigQuery in `resume_data` (asia-south1), reading straight from the bucket:

```bash
training/gcp/bigquery.sh load      # CSVs -> raw_* tables, all STRING; expire after 30 days
training/gcp/bigquery.sh profile   # counts, duplicates, blanks (bigquery/profile.sql)
training/gcp/bigquery.sh clean     # bigquery/clean.sql -> linkedin_postings, linkedin_posting_skills
training/gcp/bigquery.sh check     # invariants on the cleaned tables (all must be 0)
training/gcp/bigquery.sh export    # Parquet -> $BUCKET/cleaned/linkedin/
```

| | Rows |
|---|---|
| Raw postings | 1,348,454 |
| Search-results pages dropped (link has no job id) | 664 |
| Reposts collapsed (same title + company + description) | 271,518 |
| **`linkedin_postings`** (typed, tidied, skills array, cleaned description, `copies`) | **1,076,272** |
| with skills / with a description | 1,025,322 / 1,027,663 |
| **`linkedin_posting_skills`** (one row per posting and skill) | **21,178,274** |

Reposts matter for the catalogue: the largest group is one Dollar General
posting listed 4,571 times. `copies` keeps the count in case a weighting
wants it. The SQL is structural only (types, whitespace, HTML, duplicates);
which titles and skills count is still decided by
`scripts/build_general_catalogue.py`.

Cost: each run scans about 7 GB; the first 1 TiB of queries a month is
free. Storage: the raw tables expire after 30 days so the dataset stays inside
the free 10 GB; `load` recreates them from the bucket in about 2 minutes.

### Rebuild the role catalogue from the cleaned postings

```bash
training/gcp/bigquery.sh catalogue   # titles + skills -> $BUCKET/cleaned/linkedin_catalogue_input/ (~140 MB)
training/gcp/catalogue.sh            # build on a temporary VM, compare, delete the VM
```

`bigquery.sh catalogue` exports only the two columns the script reads, for the
postings that have skills (scans about 0.46 GB). `catalogue.sh` creates an
e2-standard-2 VM in the bucket's region, runs
`scripts/build_general_catalogue.py` and `scripts/compare_catalogues.py` on
it, deletes it, and copies the new JSON files, `compare.md` and the build log
to `ml-service/build/catalogue/<run>/`. Nothing in `app/data` changes until a
person has read `compare.md` and copied the files in; a catalogue change also
bumps `engine_version`. Cloud Shell is not used because it runs in another
region and reads this bucket at about 0.2 MB/s.

## 8. GPU training

Measured 2026-10-09; the run order and its gates are in [README.md](README.md),
"Track A run order".

### Quota

Two quotas must both allow a GPU: the project-wide `GPUS_ALL_REGIONS` (0 on a
new project; raise it to 1 under IAM & Admin → Quotas, approved within the
day) and the per-region T4 or L4 quota (already 1 in every region checked).
Free-trial billing accounts cannot use GPUs at all.

### Finding a GPU

GPUs run out per zone ("ZONE_RESOURCE_POOL_EXHAUSTED" or "STOCKOUT"). On
2026-10-09 every T4 and L4 in asia-south1 was out, and so were T4s in
asia-southeast1; an L4 in asia-southeast1-b was free. Try zones in turn and
take the first that works: a failed attempt costs nothing. Training data is
about 50 MB, so a VM in another region than the bucket costs well under a
cent in transfer. An L4 (g2-standard-4, 24 GB) is 2 to 3 times faster than a
T4, so its cost per run is similar.

```bash
for Z in asia-south1-a asia-south1-b asia-south1-c asia-southeast1-a asia-southeast1-b asia-southeast1-c; do
  gcloud compute instances create train-gpu-vm --zone=$Z --machine-type=g2-standard-4 \
    --maintenance-policy=TERMINATE \
    --image-family=pytorch-2-9-cu129-ubuntu-2404-nvidia-580 --image-project=deeplearning-platform-release \
    --boot-disk-size=100GB --service-account=$SA --scopes=cloud-platform \
    --metadata=enable-oslogin=TRUE,install-nvidia-driver=True && break
done
```

(For a T4: `--machine-type=n1-standard-4 --accelerator=type=nvidia-tesla-t4,count=1`.)
The image has the NVIDIA driver, CUDA and PyTorch; give it a minute or two
after creation before SSH answers.

### Environment

The image lacks Python's venv module. Build the venv on top of the image's
PyTorch, with the laptop's library versions:

```bash
VM=train-gpu-vm ZONE=<zone> training/gcp/push_code.sh       # from ml-service/, committed code only
# on the VM:
sudo apt-get install -y python3.12-venv
python3 -m venv --system-site-packages ~/venv
~/venv/bin/pip install -r ~/ml-service/requirements.txt transformers==4.57.6 tokenizers==0.22.2 \
  google-genai==1.75.0 pydantic-settings==2.15.0 numpy==1.26.4
```

Start long jobs detached (`nohup setsid ... &`) and poll a marker file: an SSH
session can drop or hang.

### Measured cost

L4 in Singapore, estimated at $0.90 an hour: 0.27 s per training step, 498
steps an epoch for 2,431 resumes, so the 5-epoch teacher fine-tune takes about
11 minutes (about $0.17). The whole Track A plan, three label-quality rounds
included, about 2 hours and $2 to $2.50. A running GPU VM bills even when
idle, so stop or delete it as soon as a step ends.
