#!/usr/bin/env bash
# Clean the LinkedIn postings (Kaggle "1.3M LinkedIn Jobs & Skills 2024",
# datasets/archive (4)) in BigQuery. Runs from the laptop; all work happens in
# BigQuery, which reads the CSVs straight from the bucket.
#
#   bigquery.sh load      raw CSVs -> resume_data.raw_* (every column as STRING;
#                         expire after 30 days, reload any time for free)
#   bigquery.sh profile   row counts, duplicates and blanks in the raw tables
#   bigquery.sh clean     run bigquery/clean.sql -> resume_data.linkedin_*
#   bigquery.sh check     the same counts on the cleaned tables
#   bigquery.sh export    cleaned tables -> $BUCKET/cleaned/linkedin/ (Parquet)
#   bigquery.sh catalogue titles + skills -> $BUCKET/cleaned/linkedin_catalogue_input/
#                         (gzipped JSON lines), the input of catalogue.sh
#
# Loading and exporting are free; each query's bytes are printed by a dry run
# first. The first 1 TiB of queries a month is free; this data is ~6 GB.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

DATASET=${DATASET:-resume_data}
SRC="$BUCKET/raw/archive (4)"
RAW_TTL=$((30 * 86400))  # raw copies stay in the bucket; keeps BigQuery storage in the free 10 GB
SQL_DIR="$(dirname "${BASH_SOURCE[0]}")/bigquery"
BQ=(bq --quiet --project_id="$PROJECT" --location="$REGION")

POSTINGS_COLS=job_link,last_processed_time,got_summary,got_ner,is_being_worked,job_title,company,job_location,first_seen,search_city,search_country,search_position,job_level,job_type

string_schema() { tr ',' '\n' <<<"$1" | sed 's/$/:STRING/' | paste -sd, -; }

load_csv() {  # table, file, columns
  "${BQ[@]}" load --replace --source_format=CSV --skip_leading_rows=1 \
    --allow_quoted_newlines --max_bad_records=0 --encoding=UTF-8 \
    "$DATASET.$1" "$SRC/$2" "$(string_schema "$3")"
  "${BQ[@]}" update --expiration=$RAW_TTL "$DATASET.$1"
}

run_sql() {  # file: dry run for the byte count, then the real run
  local sql
  sql=$(sed -e "s/\${DATASET}/$DATASET/g" -e "s|\${BUCKET}|$BUCKET|g" "$1")
  "${BQ[@]}" query --use_legacy_sql=false --dry_run <<<"$sql" | sed 's/^/dry run: /'
  "${BQ[@]}" query --use_legacy_sql=false --format=pretty --max_rows=100 <<<"$sql"
}

case "${1:-}" in
  load)
    "${BQ[@]}" show "$DATASET" >/dev/null 2>&1 ||
      "${BQ[@]}" mk --dataset --description "Job postings for the role catalogue" "$PROJECT:$DATASET"
    load_csv raw_postings linkedin_job_postings.csv "$POSTINGS_COLS"
    load_csv raw_skills job_skills.csv job_link,job_skills
    load_csv raw_summaries job_summary.csv job_link,job_summary
    ;;
  profile) run_sql "$SQL_DIR/profile.sql" ;;
  clean)   run_sql "$SQL_DIR/clean.sql" ;;
  check)   run_sql "$SQL_DIR/check.sql" ;;
  export)
    for t in linkedin_postings linkedin_posting_skills; do
      "${BQ[@]}" extract --destination_format=PARQUET --compression=SNAPPY \
        "$DATASET.$t" "$BUCKET/cleaned/linkedin/$t/part-*.parquet"
    done
    ;;
  catalogue)
    # Clear the old parts first: a smaller export would leave stale ones behind.
    gcloud storage rm --quiet "$BUCKET/cleaned/linkedin_catalogue_input/**" 2>/dev/null || true
    run_sql "$SQL_DIR/catalogue_input.sql"
    gcloud storage du --summarize --readable-sizes "$BUCKET/cleaned/linkedin_catalogue_input"
    ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
