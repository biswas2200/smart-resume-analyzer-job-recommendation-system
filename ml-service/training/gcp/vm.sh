#!/usr/bin/env bash
# Runs ON the data-prep VM (../gcp-setup.md §4 and §5). Inputs come from the
# bucket and results go back to it, so the VM holds nothing that cannot be
# rebuilt. Credentials are the VM's service account (Application Default
# Credentials); there is no key file.
#
#   bash vm.sh setup         Python 3.12 venv with the laptop's package versions
#   bash vm.sh test          the data-prep unit tests on this machine
#   bash vm.sh build         resume data: bucket raw/ -> ~/data/prepared -> bucket prepared/
#   bash vm.sh dry-run       labelling cost estimate for the rest of the pool (no API call)
#   bash vm.sh sample [N]    label N more pool resumes (default 5, cap $0.10)
#   bash vm.sh full          label the rest unattended (cap $MAX_USD, default 12): restarts
#                            only after a crash that made progress, writes labelled/DONE,
#                            then powers the VM off (POWER_OFF=0 to keep it running)
set -euo pipefail

BUCKET=${BUCKET:-gs://smart-resume-analyzer-a7x2-data}
export GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-smart-resume-analyzer-a7x2}
export GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION:-global}
MODEL=gemini-3.5-flash-lite
MAX_USD=${MAX_USD:-12}
CODE=$HOME/ml-service
DATA=$HOME/data
VENV=$HOME/venv
PY=$VENV/bin/python
POOL=$DATA/prepared/records/livecareer_unlabelled.jsonl
LOG=$DATA/labelled/run.log

lines() { if [ -f "$1" ]; then wc -l < "$1"; else echo 0; fi; }

setup() {
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv > /dev/null
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  # The versions in the laptop's ml-service/.venv.
  "$VENV/bin/pip" install -q google-genai==1.75.0 pydantic==2.13.5 pydantic-settings==2.15.0 pytest==8.4.2
  "$PY" --version
}

run_tests() { (cd "$CODE" && "$PY" -m pytest -q tests/test_data_prep.py); }

build() {
  # Only what build.py reads: LiveCareer's CSV, DataTurks, and the eval resumes it must leave out.
  mkdir -p "$DATA/raw/archive/Resume" "$DATA/raw/archive (1)" "$DATA/raw/eval-unseen"
  gcloud storage rsync --recursive "$BUCKET/raw/archive/Resume" "$DATA/raw/archive/Resume"
  gcloud storage rsync --recursive "$BUCKET/raw/archive (1)" "$DATA/raw/archive (1)"
  gcloud storage rsync --recursive "$BUCKET/raw/eval-unseen" "$DATA/raw/eval-unseen"
  rm -rf "$DATA/prepared"
  (cd "$CODE" && "$PY" -m training.data_prep.build --datasets-dir "$DATA/raw" --out "$DATA/prepared")
  # One fingerprint per file, so preflight.sh can compare this build with the laptop's.
  (cd "$DATA/prepared" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  gcloud storage rsync --recursive "$DATA/prepared" "$BUCKET/prepared"
}

# The output file follows the code's prompt version, so labels from two prompts never mix.
out_file() {
  local version
  version=$(cd "$CODE" && "$PY" -c 'from training.data_prep.gemini_label import PROMPT_VERSION; print(PROMPT_VERSION)')
  echo "$DATA/labelled/$MODEL.$version.jsonl"
}

prepare_labels() {
  mkdir -p "$DATA/labelled"
  # A fresh VM starts from the labels in the bucket (the laptop's sample included), so
  # finished resumes are skipped, never paid for twice. --no-clobber: a local file is
  # always newer than the bucket's copy and must never be replaced by it.
  gcloud storage cp --no-clobber "$BUCKET/labelled/$(basename "$OUT")" "$OUT" > /dev/null 2>&1 || true
  # A crash in the middle of a write can leave half a line, which the labeller cannot read.
  "$PY" - "$OUT" << 'EOF'
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes() if path.exists() else b""
if data and not data.endswith(b"\n"):
    path.write_bytes(data[: data.rfind(b"\n") + 1])
    print(f"removed a half-written last line from {path.name}")
EOF
}

sync_up() { gcloud storage cp "$OUT" "$LOG" "$BUCKET/labelled/" > /dev/null 2>&1 || true; }

label() {  # gemini_label.py on the pool with the given extra arguments
  prepare_labels
  # Copies the labels to the bucket every 5 minutes. It writes nowhere and kills its
  # own sleep when stopped: a leftover sleep holding stdout kept SSH waiting 5 minutes.
  (
    trap 'kill $! 2> /dev/null; exit 0' TERM
    while :; do
      sleep 300 &
      wait $!
      sync_up
    done
  ) > /dev/null 2>&1 &
  local syncer=$! status=0
  (cd "$CODE" && "$PY" -u -m training.data_prep.gemini_label "$POOL" --model "$MODEL" --out "$OUT" "$@") 2>&1 |
    tee -a "$LOG" || status=$?
  kill "$syncer" 2> /dev/null || true
  sync_up
  return "$status"
}

full() {
  local attempt=0 before after status
  while :; do
    prepare_labels
    before=$(lines "$OUT")
    status=0
    label --max-usd "$MAX_USD" || status=$?
    [ "$status" -eq 0 ] && break
    after=$(lines "$OUT")
    attempt=$((attempt + 1))
    # A restart pays for at most the one resume that was in flight; without progress,
    # the same failure would just repeat, so stop and leave it for a person.
    if [ "$after" -le "$before" ] || [ "$attempt" -ge 5 ]; then
      echo "giving up after $attempt failed start(s), last exit $status; see run.log" | tee -a "$LOG"
      break
    fi
    echo "labeller exited with $status after progress ($before -> $after); restarting in 60 s" | tee -a "$LOG"
    sleep 60
  done
  echo "exit=$status labelled=$(lines "$OUT") finished=$(date -Is)" | tee -a "$LOG" |
    gcloud storage cp - "$BUCKET/labelled/DONE" > /dev/null 2>&1 || true
  sync_up
  if [ "${POWER_OFF:-1}" = 1 ]; then sudo shutdown -h +1 "labelling finished"; fi
}

cmd=${1:-}
shift || true
case "$cmd" in
  setup) setup ;;
  test) run_tests ;;
  build) build ;;
  dry-run) OUT=$(out_file) && label --dry-run ;;
  sample) OUT=$(out_file) && label --limit "${1:-5}" --max-usd 0.10 ;;
  full) OUT=$(out_file) && full ;;
  *) sed -n '2,15p' "$0" && exit 2 ;;
esac
