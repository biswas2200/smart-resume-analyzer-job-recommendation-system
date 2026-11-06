-- Cleaned postings -> the input of scripts/build_general_catalogue.py
-- (bigquery.sh catalogue). One gzipped JSON line per posting that has skills:
-- {"job_title": "...", "skills": ["...", ...]}. Only the two columns the
-- script reads, so it scans and writes a fraction of the full table; postings
-- without skills are left out because the script cannot use them.
EXPORT DATA OPTIONS (
  uri = '${BUCKET}/cleaned/linkedin_catalogue_input/part-*.json.gz',
  format = 'JSON',
  compression = 'GZIP',
  overwrite = true
) AS
SELECT job_title, skills
FROM `${DATASET}.linkedin_postings`
WHERE ARRAY_LENGTH(skills) > 0;
