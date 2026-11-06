#!/usr/bin/env bash
# Downloads the trained NER models (run 1, training/RESULTS.md) from the
# project bucket into ml-service/models/ner/ and checks their weights against
# the pins below. The app serves the teacher; the student is the smaller
# alternative (NER_MODEL_NAME=models/ner/student-run1 plus its pin).
#
# Needs gcloud signed in with read access to the bucket. Model files only:
# the bucket's resumes never leave it.
set -euo pipefail

BUCKET="${BUCKET:-gs://smart-resume-analyzer-a7x2-data}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/models/ner"

# name in the bucket | local directory | SHA-256 of model.safetensors
MODELS=(
  "teacher|teacher-run1|ab0fd6ea92dee31fed5e3f56a278197e8c55a358df19328a79981b00912fe189"
  "student|student-run1|d51d3ca32c2199ebe5114a51dd48c7143f27c1abf6217d3e20333bf5b893d1c1"
)

for entry in "${MODELS[@]}"; do
  IFS='|' read -r run dir sha <<<"$entry"
  mkdir -p "$DEST/$dir"
  gcloud storage cp "$BUCKET/runs/$run/*" "$DEST/$dir/"
  echo "$sha  $DEST/$dir/model.safetensors" | sha256sum --check
done
