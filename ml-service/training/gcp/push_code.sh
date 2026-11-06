#!/usr/bin/env bash
# Laptop: puts the committed ml-service code on the VM by way of the bucket
# (../gcp-setup.md §3), with a VERSION file that preflight.sh checks. Only
# committed files travel (git archive), so no .env or local change reaches the
# VM, and the script refuses to run while a .py or .sh file is uncommitted.
set -euo pipefail
. "$(dirname "$0")/common.sh"

if [ -n "$(uncommitted_code)" ]; then
  echo "Commit these first, so the VM runs a known commit:" >&2
  uncommitted_code >&2
  exit 1
fi
commit=$(git -C "$ROOT" rev-parse HEAD)
code=$(code_fingerprint)
git -C "$ROOT" archive --format=tar.gz HEAD:ml-service | gcloud storage cp - "$BUCKET/code/ml-service-$code.tgz"
printf 'commit %s\ncode %s\n' "$commit" "$code" | gcloud storage cp - "$BUCKET/code/VERSION"
gcloud compute ssh "$VM" --zone="$ZONE" --quiet --command="set -e
rm -rf ~/ml-service && mkdir ~/ml-service
gcloud storage cat $BUCKET/code/ml-service-$code.tgz | tar xz -C ~/ml-service
gcloud storage cp $BUCKET/code/VERSION ~/ml-service/VERSION
cat ~/ml-service/VERSION"
