-- Counts and invariants on the cleaned tables (bigquery.sh check).
-- Every *_violations column must be 0.
SELECT
  COUNT(*) AS postings,
  SUM(copies) AS raw_postings_covered,
  COUNT(*) - COUNT(DISTINCT job_link) AS duplicate_link_violations,
  COUNTIF(job_title IS NULL OR job_title != TRIM(REGEXP_REPLACE(job_title, r'\s+', ' '))) AS untidy_title_violations,
  COUNTIF(first_seen IS NULL OR last_processed IS NULL) AS untyped_date_violations,
  COUNTIF(EXISTS (SELECT 1 FROM UNNEST(skills) s WHERE s = '' OR s != TRIM(s))) AS blank_skill_violations,
  COUNTIF(REGEXP_CONTAINS(summary, r'<[a-zA-Z/][^>]*>|&(amp|nbsp|lt|gt|quot);')) AS html_left,
  COUNTIF(ARRAY_LENGTH(skills) > 0) AS with_skills,
  COUNTIF(summary IS NOT NULL) AS with_summary,
  COUNTIF(copies > 1) AS kept_for_a_repost_group,
  MAX(copies) AS largest_repost_group
FROM `${DATASET}.linkedin_postings`;

SELECT
  COUNT(*) AS skill_rows,
  COUNT(DISTINCT job_link) AS postings_with_skills,
  COUNT(DISTINCT LOWER(skill)) AS distinct_skills,
  (SELECT COUNT(*) FROM (SELECT job_link, LOWER(skill) FROM `${DATASET}.linkedin_posting_skills` GROUP BY 1, 2 HAVING COUNT(*) > 1)) AS duplicate_skill_violations
FROM `${DATASET}.linkedin_posting_skills`;

-- The biggest repost groups: who posts the same job most often.
SELECT job_title, company, copies
FROM `${DATASET}.linkedin_postings` ORDER BY copies DESC LIMIT 10;

SELECT search_country, COUNT(*) AS postings, SUM(copies) AS raw
FROM `${DATASET}.linkedin_postings` GROUP BY 1 ORDER BY 2 DESC;
