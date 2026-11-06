#!/usr/bin/env bash
# Runs ON the data-prep VM next to `vm.sh full` (../gcp-setup.md §5). Waits for the
# labelling run to end, then writes a short report to Cloud Logging (log
# "labelling-report"). The alert from setup_alerts.sh emails it, so the report
# arrives with the laptop off. It must finish in the minute between the run's end
# and the VM powering itself off; it needs about 10 seconds.
#
#   nohup setsid bash report_on_finish.sh > ~/report.out 2>&1 < /dev/null &
#   bash report_on_finish.sh --dry-run      # print the report for the run so far; write nothing
set -euo pipefail

BUCKET=${BUCKET:-gs://smart-resume-analyzer-a7x2-data}
LOG=$HOME/data/labelled/run.log
LABELS=$HOME/data/labelled/gemini-3.5-flash-lite.v3.jsonl
SPENT_BEFORE=${SPENT_BEFORE:-2.06}  # USD spent on labelling before this run (LABELLING.md)
run_pid=$(pgrep -f 'vm.sh full' | head -1 || true)
STARTED=$(if [ -n "$run_pid" ]; then date -d "$(ps -o lstart= -p "$run_pid")" -Is; fi)

report() {
  python3 - "$LOG" "$LABELS" "$SPENT_BEFORE" "$STARTED" << 'EOF'
import ast
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

log_path, labels_path, spent_before, started = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
IST = timezone(timedelta(hours=5, minutes=30))
POOL = 2461

lines = open(log_path, encoding="utf-8").read().splitlines()
starts = [i for i, line in enumerate(lines) if re.match(r"\d+ resumes to label", line) and "cap $12" in line]
run = lines[starts[0]:] if starts else []
done = [line for line in run if re.match(r"  livecareer-\d+:", line)]
cost = sum(float(re.search(r"\$([\d.]+) \(assumed", line).group(1)) for line in done)
assumed = sum(float(re.search(r"\(assumed \$([\d.]+)\)", line).group(1)) for line in done)
retries = Counter(m.group(1) for line in run if (m := re.match(r"  (\d{3}) from Vertex AI", line)))
alignment = Counter()
for line in run:
    if line.startswith("alignment: "):
        alignment.update(ast.literal_eval(line[len("alignment: "):]))
end = next((line for line in reversed(run) if line.startswith("exit=")), "")
fields = dict(part.split("=", 1) for part in end.split()) if end else {}

labels, records = Counter(), 0
with open(labels_path, encoding="utf-8") as handle:
    for line in handle:
        if line.strip():
            records += 1
            labels.update(entity["label"] for entity in json.loads(line)["entities"])

n = len(done)
if not end:
    headline = f"in progress (dry run): {n} labelled this run, {records:,} of {POOL:,} in total"
elif fields.get("exit") == "0" and records == POOL:
    headline = f"finished, all {POOL:,} pool resumes labelled for ${cost:.2f}"
else:
    headline = f"stopped early (exit {fields.get('exit')}): {records:,} of {POOL:,} labelled, ${cost:.2f} spent"

span = ""
if started and fields.get("finished"):
    t0, t1 = datetime.fromisoformat(started), datetime.fromisoformat(fields["finished"])
    minutes = int((t1 - t0).total_seconds() // 60)
    span = f" in {minutes // 60}h{minutes % 60:02d}m ({t0.astimezone(IST):%H:%M} to {t1.astimezone(IST):%H:%M} IST)"
answers = alignment["answers"]
report = {
    "headline": headline,
    "run": (f"{n:,} resumes this run{span}; ${cost:.2f} actual vs ${assumed:.2f} estimated "
            f"(${cost / max(n, 1):.4f} per resume); retries: "
            + (", ".join(f"{code} x{count}" for code, count in sorted(retries.items())) or "none")
            + f"; restarts {len(starts) - 1}"),
    "quality": (f"{answers:,} answers; {alignment['not_in_text']:,} not found in the text "
                f"({100 * alignment['not_in_text'] / max(answers, 1):.2f} %); "
                f"{alignment['placeholder_dropped']:,} placeholders dropped; {alignment['overlap_dropped']:,} overlaps dropped; "
                f"graduation years {alignment['graduation_year_dropped']:,} dropped, {alignment['graduation_year_added']:,} added; "
                f"{alignment['entities_kept']:,} entities kept"
                + ("; every record passed validation" if fields.get("exit") == "0" else "")),
    "labels": f"{records:,} records; " + "; ".join(f"{label} {count:,}" for label, count in labels.most_common()),
    "budget": (f"labelling spend to date about ${spent_before + cost:.2f} of the $20 budget "
               f"(${spent_before:.2f} before this run)"),
    "next": ("the VM powers itself off now. Then: training/gcp/preflight.sh after, "
             "record the spend in LABELLING.md, delete the VM when the data work is done"),
}
print(json.dumps(report, ensure_ascii=False))
EOF
}

if [ "${1:-}" = --dry-run ]; then
  report
  exit 0
fi

# Only an exit line written after this script started counts.
skip=$(wc -l < "$LOG")
until awk -v skip="$skip" 'NR > skip && /^exit=/ {found = 1} END {exit !found}' "$LOG"; do sleep 5; done
json=$(report)
for attempt in 1 2 3; do
  gcloud logging write labelling-report "$json" --payload-type=json --severity=NOTICE && break
  sleep 5
done
echo "$json" | gcloud storage cp - "$BUCKET/labelled/REPORT.json" || true
echo "report written at $(date -Is)"
