#!/usr/bin/env bash
# Read-only checks before each stage of the GCP data work (../PREFLIGHT.md).
# Creates, changes and deletes nothing, and calls no paid API. Run on the laptop:
#
#   ml-service/training/gcp/preflight.sh setup|data|vm|label|after
set -uo pipefail
. "$(dirname "$0")/common.sh"

DATASETS=${DATASETS:-$ROOT/datasets}
LABELS=gemini-3.5-flash-lite.v3.jsonl
POOL=$DATASETS/prepared/records/livecareer_unlabelled.jsonl
# The commit whose labelling logic the 10-resume sample and LABELLING.md's numbers measured.
MEASURED=6f8d308
# What the upload in gcp-setup.md §2 leaves out: build outputs, caches, editor lock files.
EXCLUDE='^(prepared|labelled)/.*|.*__pycache__/.*|.*\.~lock\..*'

failed=0
check() {  # check "what is checked" command [args...]
  local what=$1
  shift
  if "$@" > /dev/null 2>&1; then echo "  PASS  $what"; else echo "  FAIL  $what"; failed=$((failed + 1)); fi
}

# --- setup ----------------------------------------------------------------------

active_account() { [ -n "$(gcloud auth list --filter=status:ACTIVE --format='value(account)')" ]; }
project_is_set() { [ "$(gcloud config get-value project 2> /dev/null)" = "$PROJECT" ]; }
adc_works() { gcloud auth application-default print-access-token > /dev/null; }
adc_quota_project() {
  python3 -I -c 'import json, os, sys
path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
sys.exit(json.load(open(path)).get("quota_project_id") != sys.argv[1])' "$PROJECT"
}
billing_enabled() { [ "$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)')" = True ]; }
budget_exists() {
  local account
  account=$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)')
  [ -n "$(gcloud billing budgets list --billing-account="${account#billingAccounts/}" --format='value(name)')" ]
}
api_enabled() { gcloud services list --enabled --project="$PROJECT" --format='value(config.name)' | grep -qx "$1"; }
code_committed() { [ -z "$(uncommitted_code)" ]; }

stage_setup() {
  echo "setup: before creating anything"
  check "gcloud has an active account" active_account
  check "gcloud project is $PROJECT" project_is_set
  check "Application Default Credentials issue a token" adc_works
  check "ADC quota project is $PROJECT" adc_quota_project
  check "billing is enabled" billing_enabled
  check "a budget alert exists on the billing account" budget_exists
  local api
  for api in compute.googleapis.com storage.googleapis.com aiplatform.googleapis.com; do
    check "$api is enabled" api_enabled "$api"
  done
  check "no uncommitted .py/.sh change under ml-service (the VM runs a known commit)" code_committed
}

# --- data -----------------------------------------------------------------------

bucket_field() { gcloud storage buckets describe "$BUCKET" --format="value($1)"; }
bucket_in_region() { [ "$(bucket_field location)" = "${REGION^^}" ]; }
bucket_private() {
  [ "$(bucket_field uniform_bucket_level_access)" = True ] &&
    [ "$(bucket_field public_access_prevention)" = enforced ]
}
soft_delete_on() { [ "$(bucket_field soft_delete_policy.retentionDurationSeconds)" -ge 604800 ]; }
raw_copy_complete() {
  # A dry run lists what an upload would still copy; complete means nothing.
  local plan
  plan=$(gcloud storage rsync --recursive --dry-run --exclude="$EXCLUDE" "$DATASETS" "$BUCKET/raw" 2>&1) || return 1
  ! grep -qi "would copy" <<< "$plan"
}
paid_labels_uploaded() {
  # The bucket's file must start with the laptop's labelled resumes (it grows on the VM).
  local local_file=$DATASETS/labelled/$LABELS
  cmp -s -n "$(stat -c %s "$local_file")" "$local_file" <(gcloud storage cat "$BUCKET/labelled/$LABELS")
}

stage_data() {
  echo "data: the datasets in the bucket"
  check "bucket is in ${REGION^^}" bucket_in_region
  check "bucket is private (uniform access, public access prevention enforced)" bucket_private
  check "soft delete keeps deleted or overwritten files for 7 days or more" soft_delete_on
  check "raw/ holds every file in datasets/ (rsync dry run would copy nothing)" raw_copy_complete
  check "the 10 paid labels from the laptop are in labelled/" paid_labels_uploaded
}

# --- vm -------------------------------------------------------------------------

sa_exists() { gcloud iam service-accounts describe "$SA"; }
sa_project_roles_minimal() {
  [ "$(gcloud projects get-iam-policy "$PROJECT" --flatten='bindings[].members' \
    --filter="bindings.members:serviceAccount:$SA" --format='value(bindings.role)' | sort | paste -sd,)" \
    = roles/aiplatform.user,roles/logging.logWriter ]
}
sa_bucket_role() {
  gcloud storage buckets get-iam-policy "$BUCKET" --format=json | python3 -I -c 'import json, sys
member = "serviceAccount:" + sys.argv[1]
bindings = json.load(sys.stdin).get("bindings", [])
sys.exit(not any(b["role"] == "roles/storage.objectAdmin" and member in b["members"] for b in bindings))' "$SA"
}
vm_field() { gcloud compute instances describe "$VM" --zone="$ZONE" --format="value($1)"; }
vm_running() { [ "$(vm_field status)" = RUNNING ]; }
vm_uses_sa() { [ "$(vm_field 'serviceAccounts[0].email')" = "$SA" ]; }
vm_no_gpu() { [ -z "$(vm_field guestAccelerators)" ]; }
vm_not_spot() { [ "$(vm_field scheduling.provisioningModel)" != SPOT ]; }
on_vm() { gcloud compute ssh "$VM" --zone="$ZONE" --quiet --command="$1" 2> /dev/null; }
vm_code_matches() { [ "$(on_vm 'sed -n "s/^code //p" ~/ml-service/VERSION')" = "$(code_fingerprint)" ]; }
vm_python_312() { on_vm '~/venv/bin/python -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))"'; }

stage_vm() {
  echo "vm: service account and VM"
  check "service account $SA exists" sa_exists
  check "its only project roles are aiplatform.user and logging.logWriter" sa_project_roles_minimal
  check "it has roles/storage.objectAdmin on the bucket" sa_bucket_role
  check "VM $VM is running in $ZONE" vm_running
  check "VM runs as the service account" vm_uses_sa
  check "VM has no GPU" vm_no_gpu
  check "VM is not Spot (a Spot stop would halt an unattended run)" vm_not_spot
  check "VM code = the laptop's committed .py/.sh files" vm_code_matches
  check "VM venv is Python 3.12, as on the laptop" vm_python_312
}

# --- label ----------------------------------------------------------------------

vm_build_matches_laptop() {
  local sums
  sums=$(gcloud storage cat "$BUCKET/prepared/SHA256SUMS") && [ -n "$sums" ] || return 1
  (cd "$DATASETS/prepared" && sha256sum --check --quiet <<< "$sums") &&
    [ "$(cd "$DATASETS/prepared" && find . -type f ! -name SHA256SUMS | sort)" = "$(awk '{print $2}' <<< "$sums" | sort)" ]
}
eval_resumes_excluded() {
  # Checked on the laptop's build, which the check before proved identical to the VM's.
  # The eval file stores bare LiveCareer IDs; the pool prefixes them with "livecareer-".
  python3 -I - "$DATASETS" << 'EOF'
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
def read(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
unseen = {"livecareer-" + str(r["id"]) for r in read(d / "eval-unseen/sample.jsonl")}
pool = {r["id"] for r in read(d / "prepared/records/livecareer_unlabelled.jsonl")}
turks_test = {r["id"] for r in read(d / "prepared/records/dataturks.jsonl") if r["split"] == "test"}
ok = len(unseen) == 20 and not unseen & pool and {f"dataturks-{i:04d}" for i in range(111, 131)} <= turks_test
sys.exit(not ok)
EOF
}
labelling_logic_unchanged() {
  # Everything in gemini_label.py except the module docstring and the retry helper,
  # plus the helpers it imports, must be identical to the measured commit.
  local file=ml-service/training/data_prep/gemini_label.py
  git -C "$ROOT" diff --quiet "$MEASURED" HEAD -- ml-service/training/data_prep/dataturks.py \
    ml-service/training/data_prep/schema.py || return 1
  python3 -I - <(git -C "$ROOT" show "$MEASURED:$file") <(git -C "$ROOT" show "HEAD:$file") << 'EOF'
import ast
import sys

def shape(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    body = [n for n in tree.body[1:] if not (isinstance(n, ast.FunctionDef) and n.name == "_with_retry")]
    return ast.dump(ast.Module(body=body, type_ignores=[]))

sys.exit(shape(sys.argv[1]) != shape(sys.argv[2]))
EOF
}

report_alert_ready() {
  # Enabled, and every channel it emails is verified: Google silently drops alert
  # emails to an unverified channel (found 2026-10-09: two test alerts never arrived).
  local channels channel
  [ "$(gcloud monitoring policies list --project="$PROJECT" \
    --filter='displayName="Data work: labelling report"' --format='value(enabled)')" = True ] || return 1
  channels=$(gcloud monitoring policies list --project="$PROJECT" \
    --filter='displayName="Data work: labelling report"' --format='value(notificationChannels.list(separator=" "))')
  [ -n "$channels" ] || return 1
  for channel in $channels; do
    [ "$(gcloud beta monitoring channels describe "$channel" --format='value(verificationStatus)')" = VERIFIED ] || return 1
  done
}
report_watcher_running() { on_vm 'pgrep -f "bash .*report_on_finish.sh$"'; }

stage_label() {
  echo "label: before the full labelling run"
  check "VM build = laptop build, file by file (SHA-256)" vm_build_matches_laptop
  check "eval resumes are not in the pool; DataTurks 0111-0130 are in test" eval_resumes_excluded
  check "labelling logic is unchanged since the measured sample ($MEASURED)" labelling_logic_unchanged
  check "the report email alert is enabled and its email channel verified (setup_alerts.sh)" report_alert_ready
  check "report_on_finish.sh is waiting on the VM, so the report arrives with the laptop off" report_watcher_running
  echo "  by hand: dry-run estimate x the sample's actual/assumed <= cap; VM sample <= \$0.007 per resume,"
  echo "           not_in_text <= 1 %; spent so far + estimate <= \$20 (PREFLIGHT.md 4.4 to 4.6)"
}

# --- after ----------------------------------------------------------------------

run_finished_cleanly() { gcloud storage cat "$BUCKET/labelled/DONE" | grep -q '^exit=0 '; }
pool_fully_labelled() {
  [ "$(gcloud storage cat "$BUCKET/labelled/$LABELS" | wc -l)" -eq "$(wc -l < "$POOL")" ]
}
vm_stopped() { [ "$(vm_field status 2> /dev/null)" != RUNNING ]; }

stage_after() {
  echo "after: the labelling run"
  check "labelled/DONE reports exit=0" run_finished_cleanly
  check "every pool resume is labelled ($(wc -l < "$POOL"))" pool_fully_labelled
  check "VM is not running" vm_stopped
  echo "  by hand: quality numbers, 3 records by eye, spend recorded (PREFLIGHT.md 5.4 to 5.6)"
}

case ${1:-} in
  setup) stage_setup ;;
  data) stage_data ;;
  vm) stage_vm ;;
  label) stage_label ;;
  after) stage_after ;;
  *) sed -n '2,5p' "$0" && exit 2 ;;
esac
echo
if [ "$failed" -eq 0 ]; then echo "All automated checks passed."; else echo "$failed check(s) failed: fix them before going on." && exit 1; fi
