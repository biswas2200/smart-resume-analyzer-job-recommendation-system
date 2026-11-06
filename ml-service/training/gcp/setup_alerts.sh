#!/usr/bin/env bash
# Laptop: email alerts for the data work (../gcp-setup.md §5), so the labelling
# report reaches you with the laptop off. Creates each of these once; running the
# script again creates nothing new:
#   - a Cloud Monitoring email channel to ADDRESS. Google silently drops alert
#     emails to an unverified channel, so the first run emails a verification
#     code and stops; run it again with that code to verify the channel;
#   - "Data work: labelling report": emails the report that report_on_finish.sh
#     writes to Cloud Logging when the run ends;
#   - "Data work: data-prep VM stopped": emails when the VM shuts down or is stopped,
#     a backstop in case no report arrives;
#   - "Data work: catalogue report": emails the report that catalogue.sh's VM
#     writes when a role catalogue rebuild ends.
#
#   ml-service/training/gcp/setup_alerts.sh you@example.com            # emails a code
#   ml-service/training/gcp/setup_alerts.sh you@example.com G-123456   # verifies, then the alerts
set -euo pipefail
. "$(dirname "$0")/common.sh"
EMAIL=${1:?usage: setup_alerts.sh EMAIL_ADDRESS [VERIFICATION_CODE]}
CODE=${2:-}

channel=$(gcloud beta monitoring channels list --project="$PROJECT" \
  --filter="type=\"email\" AND labels.email_address=\"$EMAIL\"" --format='value(name)' | head -1)
if [ -z "$channel" ]; then
  channel=$(gcloud beta monitoring channels create --project="$PROJECT" --type=email \
    --display-name="Data work email" --channel-labels=email_address="$EMAIL" --format='value(name)')
fi
echo "channel: $channel"

# gcloud has no command for channel verification; the REST API does.
channel_api() {  # channel_api METHOD JSON_BODY
  curl -sf -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" -H "x-goog-user-project: $PROJECT" \
    -d "$2" "https://monitoring.googleapis.com/v3/$channel:$1"
}
status=$(gcloud beta monitoring channels describe "$channel" --format='value(verificationStatus)')
if [ "$status" != VERIFIED ]; then
  if [ -z "$CODE" ]; then
    channel_api sendVerificationCode '{}' > /dev/null
    echo "Sent a verification code to $EMAIL (subject: Your alerting verification code)."
    echo "Run again with it: $0 $EMAIL G-XXXXXX"
    exit 1
  fi
  channel_api verify "{\"code\": \"$CODE\"}" > /dev/null
  echo "channel verified"
fi

create_policy() {  # create_policy DISPLAY_NAME < policy JSON with __PROJECT__ __CHANNEL__ __BUCKET__ __VM__
  local name=$1 file
  if [ -n "$(gcloud monitoring policies list --project="$PROJECT" --filter="displayName=\"$name\"" --format='value(name)')" ]; then
    echo "exists: $name"
    cat > /dev/null
    return
  fi
  file=$(mktemp)
  sed -e "s|__PROJECT__|$PROJECT|g" -e "s|__CHANNEL__|$channel|g" -e "s|__BUCKET__|${BUCKET#gs://}|g" \
    -e "s|__VM__|$VM|g" > "$file"
  gcloud monitoring policies create --project="$PROJECT" --policy-from-file="$file" --format='value(name)'
  rm -f "$file"
}

create_policy "Data work: labelling report" << 'EOF'
{
  "displayName": "Data work: labelling report",
  "combiner": "OR",
  "conditions": [{
    "displayName": "report_on_finish.sh wrote the labelling report",
    "conditionMatchedLog": {
      "filter": "logName=\"projects/__PROJECT__/logs/labelling-report\"",
      "labelExtractors": {
        "headline": "EXTRACT(jsonPayload.headline)",
        "run": "EXTRACT(jsonPayload.run)",
        "quality": "EXTRACT(jsonPayload.quality)",
        "labels": "EXTRACT(jsonPayload.labels)",
        "budget": "EXTRACT(jsonPayload.budget)",
        "next": "EXTRACT(jsonPayload.next)"
      }
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "300s"}, "autoClose": "1800s", "notificationPrompts": ["OPENED"]},
  "notificationChannels": ["__CHANNEL__"],
  "documentation": {
    "mimeType": "text/markdown",
    "subject": "[Smart Resume Analyser] Labelling run ${log.extracted_label.headline}",
    "content": "**Labelling run ${log.extracted_label.headline}**\n\n- **Run:** ${log.extracted_label.run}\n- **Quality:** ${log.extracted_label.quality}\n- **Entities by label:** ${log.extracted_label.labels}\n- **Budget:** ${log.extracted_label.budget}\n- **Next:** ${log.extracted_label.next}\n\nFull log and this report: gs://__BUCKET__/labelled/ (run.log, REPORT.json)"
  }
}
EOF

create_policy "Data work: data-prep VM stopped" << 'EOF'
{
  "displayName": "Data work: data-prep VM stopped",
  "combiner": "OR",
  "conditions": [{
    "displayName": "data-prep VM shut down or was stopped",
    "conditionMatchedLog": {
      "filter": "resource.type=\"gce_instance\" AND protoPayload.resourceName:\"instances/__VM__\" AND (protoPayload.methodName:\"guestTerminate\" OR protoPayload.methodName:\"instances.stop\" OR protoPayload.methodName:\"instances.preempted\")"
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "300s"}, "autoClose": "1800s", "notificationPrompts": ["OPENED"]},
  "notificationChannels": ["__CHANNEL__"],
  "documentation": {
    "mimeType": "text/markdown",
    "subject": "[Smart Resume Analyser] data-prep VM stopped",
    "content": "The data-prep VM has stopped, so it no longer bills for compute (its disk still does, under $1 a month). A labelling report should arrive in its own email; if none does, check gs://__BUCKET__/labelled/DONE and run.log."
  }
}
EOF

create_policy "Data work: catalogue report" << 'EOF'
{
  "displayName": "Data work: catalogue report",
  "combiner": "OR",
  "conditions": [{
    "displayName": "catalogue.sh wrote the catalogue report",
    "conditionMatchedLog": {
      "filter": "logName=\"projects/__PROJECT__/logs/catalogue-report\"",
      "labelExtractors": {
        "headline": "EXTRACT(jsonPayload.headline)",
        "results": "EXTRACT(jsonPayload.results)",
        "where": "EXTRACT(jsonPayload.where)",
        "next": "EXTRACT(jsonPayload.next)"
      }
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "300s"}, "autoClose": "1800s", "notificationPrompts": ["OPENED"]},
  "notificationChannels": ["__CHANNEL__"],
  "documentation": {
    "mimeType": "text/markdown",
    "subject": "[Smart Resume Analyser] Role catalogue rebuild ${log.extracted_label.headline}",
    "content": "**Role catalogue rebuild ${log.extracted_label.headline}**\n\n- **Results** (new build vs the app's current catalogue): ${log.extracted_label.results}\n- **Files:** ${log.extracted_label.where} (compare.md per input, run.log)\n- **Next:** ${log.extracted_label.next}"
  }
}
EOF
