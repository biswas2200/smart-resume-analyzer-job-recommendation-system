#!/usr/bin/env bash
# Laptop: rebuild the general role catalogue from the cleaned LinkedIn postings
# on a temporary VM next to the bucket. The VM does the whole job on its own,
# emails a report (setup_alerts.sh, "Data work: catalogue report") and powers
# itself off, so the laptop can be closed once `start` returns. Export the
# input first with `bigquery.sh catalogue`.
#
#   catalogue.sh start [--limit N]   upload the code, create the VM; prints the run id
#   catalogue.sh fetch RUN           copy the results to ml-service/build/catalogue/RUN/
#                                    (git-ignored) and delete the powered-off VM
#
# Each input is built and compared with the app's current catalogue
# (scripts/compare_catalogues.py); per input the run keeps the two JSON files,
# compare.md and build.log, plus run.log for the whole run. app/data is not
# touched: copy the files there only after compare.md has been reviewed.
# INPUTS="name=gs://... ..." builds from other exports of the same shape
# (default: cleaned=$BUCKET/cleaned/linkedin_catalogue_input).
#
# Why a VM and not Cloud Shell: Cloud Shell runs in another region and reads
# this bucket at about 0.2 MB/s (measured 2026-10-10). An e2-standard-2 in the
# bucket's region costs about $0.08 an hour while it runs; once it has powered
# off, only its 10 GB disk bills (about 3 cents a day) until `fetch` deletes it.
set -euo pipefail

if [ "${1:-}" = --remote ]; then  # on the VM, as root, called by the startup script below
  run_uri=$2
  work=$(mktemp -d)
  mkdir -p "$work/ml-service/scripts" "$work/ml-service/app/data" "$work/old"
  gcloud storage cp --quiet "$run_uri/code/*.py" "$work/ml-service/scripts/"
  gcloud storage cp --quiet "$run_uri/code/domains.json" "$work/ml-service/app/data/"
  gcloud storage cp --quiet "$run_uri/old/*" "$work/old/"
  gcloud storage cp --quiet "$run_uri/inputs.txt" "$run_uri/args.txt" "$work/"
  cd "$work/ml-service"
  python3 --version
  status=0
  : > /root/results.txt
  # fd 3, so gcloud and python cannot swallow the rest of inputs.txt from stdin.
  while read -r name input <&3; do
    mkdir -p "$work/input/$name" "$work/new/$name"
    SECONDS=0
    # shellcheck disable=SC2046  # args.txt is a list of options, split on purpose
    if gcloud storage cp --quiet "$input/*.json.gz" "$work/input/$name/" &&
      python3 scripts/build_general_catalogue.py --input "$work/input/$name" --out-dir "$work/new/$name" \
        $(cat "$work/args.txt") 2>&1 | tee "$work/new/$name/build.log"; then
      echo "build took ${SECONDS}s" | tee -a "$work/new/$name/build.log"
      python3 scripts/compare_catalogues.py "$work/old" "$work/new/$name" > "$work/new/$name/compare.md"
      echo "$name: $(python3 scripts/compare_catalogues.py --summary "$work/old" "$work/new/$name") [${SECONDS}s]" \
        >> /root/results.txt
    else
      status=1
      echo "$name: FAILED, see $name/build.log" >> /root/results.txt
    fi
    gcloud storage cp --quiet --recursive "$work/new/$name" "$run_uri/out/"
  done 3< "$work/inputs.txt"
  exit "$status"
fi

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ML=$ROOT/ml-service
CATALOGUE_VM=${CATALOGUE_VM:-catalogue-vm}

case "${1:-}" in
  start)
    shift
    INPUTS=${INPUTS:-cleaned=$BUCKET/cleaned/linkedin_catalogue_input}
    RUN=$(date -u +%Y%m%dT%H%M%SZ)
    RUN_URI=$BUCKET/catalogue/$RUN
    OUT=$ML/build/catalogue/$RUN
    mkdir -p "$OUT"
    for pair in $INPUTS; do
      gcloud storage ls "${pair#*=}/*.json.gz" > /dev/null ||
        { echo "no *.json.gz in ${pair#*=}: run bigquery.sh catalogue first" >&2; exit 1; }
      echo "${pair%%=*} ${pair#*=}"
    done > "$OUT/inputs.txt"
    echo "$*" > "$OUT/args.txt"
    {
      echo "run $RUN"
      echo "inputs $INPUTS"
      echo "args $*"
      dirty=$(git -C "$ROOT" status --porcelain -- ml-service/scripts ml-service/app/data ml-service/training/gcp)
      echo "commit $(git -C "$ROOT" rev-parse HEAD)${dirty:+ plus uncommitted changes, so the hashes below are what ran}"
      (cd "$ML" && sha256sum scripts/build_general_catalogue.py scripts/compare_catalogues.py app/data/domains.json \
        app/data/role_skills_general.json app/data/skill_taxonomy_general.json)
    } > "$OUT/BUILD_INFO"
    # Runs once at boot, as root: the job, the report that setup_alerts.sh emails, power off.
    cat > "$OUT/startup.sh" << 'EOF'
#!/bin/bash
[ -e /var/lib/catalogue-done ] && exit 0
touch /var/lib/catalogue-done
run_uri=$(curl -sf -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/run-uri)
SECONDS=0
{ gcloud storage cp --quiet "$run_uri/code/catalogue.sh" /root/catalogue.sh &&
  bash /root/catalogue.sh --remote "$run_uri"; } > /root/run.log 2>&1
status=$?
gcloud storage cp --quiet /root/run.log "$run_uri/out/run.log"
python3 - "$status" "$run_uri" "$SECONDS" > /root/report.json << 'PY'
import json, os, sys
status, run_uri, seconds = sys.argv[1], sys.argv[2], int(sys.argv[3])
path = "/root/results.txt"
results = open(path).read().split("\n") if os.path.exists(path) else []
print(json.dumps({
    "headline": ("finished" if status == "0" else f"failed (exit {status})") + f" in {seconds // 60} min",
    "results": " || ".join(r for r in results if r) or "no results; see run.log",
    "where": f"{run_uri}/out/",
    "next": f"the VM has powered itself off. On the laptop: training/gcp/catalogue.sh fetch "
            f"{run_uri.rsplit('/', 1)[1]} (copies the results, deletes the VM), then review compare.md",
}))
PY
for attempt in 1 2 3; do
  gcloud logging write catalogue-report "$(cat /root/report.json)" --payload-type=json --severity=NOTICE && break
  sleep 5
done
poweroff
EOF
    gcloud storage cp --quiet "$ML/scripts/build_general_catalogue.py" "$ML/scripts/compare_catalogues.py" \
      "$ML/app/data/domains.json" "${BASH_SOURCE[0]}" "$RUN_URI/code/"
    gcloud storage cp --quiet "$ML/app/data/role_skills_general.json" "$ML/app/data/skill_taxonomy_general.json" \
      "$RUN_URI/old/"
    gcloud storage cp --quiet "$OUT/BUILD_INFO" "$OUT/inputs.txt" "$OUT/args.txt" "$RUN_URI/"
    # Ubuntu 24.04 has Python 3.12, the laptop's version. The VM acts as the
    # data-prep service account: this bucket, Vertex AI, and writing logs (gcp-setup.md §3).
    gcloud compute instances create "$CATALOGUE_VM" --zone="$ZONE" --machine-type=e2-standard-2 \
      --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=10GB \
      --service-account="$SA" --scopes=cloud-platform \
      --metadata=enable-oslogin=TRUE,run-uri="$RUN_URI" --metadata-from-file=startup-script="$OUT/startup.sh"
    echo "run $RUN started on $CATALOGUE_VM; the laptop can be closed."
    echo "An email arrives when it ends. Then: training/gcp/catalogue.sh fetch $RUN"
    ;;
  fetch)
    RUN=${2:?usage: catalogue.sh fetch RUN}
    OUT=$ML/build/catalogue/$RUN
    state=$(gcloud compute instances describe "$CATALOGUE_VM" --zone="$ZONE" --format='value(status)' 2> /dev/null || true)
    if [ "$state" = RUNNING ]; then
      echo "$CATALOGUE_VM is still running; wait for the email" >&2
      exit 1
    fi
    mkdir -p "$OUT"
    gcloud storage cp --quiet --recursive "$BUCKET/catalogue/$RUN/out/*" "$OUT/"
    [ -n "$state" ] && gcloud compute instances delete "$CATALOGUE_VM" --zone="$ZONE" --quiet
    echo "results in $OUT"
    for f in "$OUT"/*/compare.md; do
      echo "== $f"
      sed -n '3,12p' "$f"
    done
    ;;
  *)
    sed -n '2,22p' "$0"
    exit 2
    ;;
esac
