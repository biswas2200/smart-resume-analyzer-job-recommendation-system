-- What the raw LinkedIn tables look like before cleaning (bigquery.sh profile).
SELECT
  'raw_postings' AS tbl,
  COUNT(*) AS n_rows,
  COUNT(DISTINCT job_link) AS distinct_links,
  COUNT(DISTINCT REGEXP_EXTRACT(job_link, r'-(\d+)$')) AS distinct_job_ids,
  COUNTIF(REGEXP_EXTRACT(job_link, r'-(\d+)$') IS NULL) AS links_without_id,
  COUNTIF(TRIM(IFNULL(job_title, '')) = '') AS blank_titles,
  COUNTIF(job_title != TRIM(REGEXP_REPLACE(job_title, r'\s+', ' '))) AS untidy_titles,
  COUNTIF(SAFE.PARSE_DATE('%Y-%m-%d', first_seen) IS NULL) AS bad_first_seen,
  MIN(first_seen) AS first_seen_min,
  MAX(first_seen) AS first_seen_max
FROM `${DATASET}.raw_postings`;

SELECT search_country, job_level, job_type, got_summary, got_ner, COUNT(*) AS n
FROM `${DATASET}.raw_postings`
GROUP BY 1, 2, 3, 4, 5 ORDER BY n DESC LIMIT 30;

SELECT
  'raw_skills' AS tbl,
  COUNT(*) AS n_rows,
  COUNT(DISTINCT job_link) AS distinct_links,
  COUNTIF(TRIM(IFNULL(job_skills, '')) = '') AS blank,
  COUNTIF(job_link NOT IN (SELECT job_link FROM `${DATASET}.raw_postings`)) AS orphan_links,
  ROUND(AVG(ARRAY_LENGTH(SPLIT(job_skills, ','))), 1) AS avg_skills
FROM `${DATASET}.raw_skills`;

SELECT
  'raw_summaries' AS tbl,
  COUNT(*) AS n_rows,
  COUNT(DISTINCT job_link) AS distinct_links,
  COUNTIF(TRIM(IFNULL(job_summary, '')) = '') AS blank,
  COUNTIF(job_link NOT IN (SELECT job_link FROM `${DATASET}.raw_postings`)) AS orphan_links,
  COUNTIF(REGEXP_CONTAINS(job_summary, r'<[a-zA-Z/][^>]*>')) AS with_html_tags,
  COUNTIF(REGEXP_CONTAINS(job_summary, r'&(amp|nbsp|lt|gt|quot|#\d+);')) AS with_html_entities,
  COUNTIF(LENGTH(job_summary) < 200) AS under_200_chars,
  CAST(APPROX_QUANTILES(LENGTH(job_summary), 2)[OFFSET(1)] AS INT64) AS median_chars
FROM `${DATASET}.raw_summaries`;

-- Same posting under more than one link (same numeric job id)?
SELECT COUNT(*) AS ids_with_several_links, SUM(n) AS rows_involved
FROM (
  SELECT REGEXP_EXTRACT(job_link, r'-(\d+)$') AS job_id, COUNT(*) AS n
  FROM `${DATASET}.raw_postings` GROUP BY 1 HAVING n > 1
);
