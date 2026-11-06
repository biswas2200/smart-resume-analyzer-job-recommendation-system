-- Raw LinkedIn tables -> cleaned tables (bigquery.sh clean). Rebuilds from
-- scratch every run; the raw tables are never modified.
--
--   linkedin_postings        one row per distinct posting: typed columns,
--                            tidied title, skills array, cleaned description,
--                            and copies = how many raw postings it stands for
--   linkedin_posting_skills  (job_link, skill), one row per skill
--
-- What is removed, and why (numbers from the 2026-10-10 profile):
--   * links without a numeric job id (664): search-results pages such as
--     /jobs/cashier-jobs, not postings; their title often differs from the slug
--   * reposts (~269K): the same title + company + description text under
--     another link, mostly agencies posting one job in many cities. One copy is
--     kept (earliest first_seen) so a role isn't counted once per city.
--     Without a description, title + company + location decides instead.
-- Domain rules (which titles and skills count) stay in
-- scripts/build_general_catalogue.py; this step is structural only.

CREATE TEMP FUNCTION tidy(s STRING) AS (
  NULLIF(TRIM(REGEXP_REPLACE(s, r'\s+', ' ')), '')
);

CREATE TEMP FUNCTION clean_text(s STRING) AS (
  NULLIF(TRIM(
    REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(
      REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        REGEXP_REPLACE(REGEXP_REPLACE(s, r'(?i)<br\s*/?>|</p>|</li>', '\n'), r'<[a-zA-Z/][^>]*>', ''),
        '&nbsp;', ' '), '&lt;', '<'), '&gt;', '>'), '&quot;', '"'), '&#39;', "'"), '&apos;', "'"), '&amp;amp;', '&'), '&amp;', '&'),
      r'[ \t\x{00A0}]+', ' '),           -- runs of spaces
      r' *\n *', '\n'),                  -- spaces around line breaks
      r'\n{3,}', '\n\n')                 -- at most one blank line
  ), '')
);

CREATE TEMP FUNCTION skill_list(s STRING) AS (
  -- split, tidy, drop blanks, keep the first spelling of each skill
  ARRAY(
    SELECT ANY_VALUE(skill) FROM (
      SELECT tidy(part) AS skill, pos
      FROM UNNEST(SPLIT(IFNULL(s, ''), ',')) AS part WITH OFFSET pos
    )
    WHERE skill IS NOT NULL
    GROUP BY LOWER(skill)
    ORDER BY MIN(pos)
  )
);

CREATE TEMP TABLE typed AS
SELECT
  p.job_link,
  REGEXP_EXTRACT(p.job_link, r'-(\d+)$') AS job_id,
  tidy(p.job_title) AS job_title,
  tidy(p.company) AS company,
  tidy(p.job_location) AS job_location,
  tidy(p.search_city) AS search_city,
  tidy(p.search_country) AS search_country,
  tidy(p.search_position) AS search_position,
  tidy(p.job_level) AS job_level,
  tidy(p.job_type) AS job_type,
  SAFE.PARSE_DATE('%Y-%m-%d', p.first_seen) AS first_seen,
  SAFE_CAST(p.last_processed_time AS TIMESTAMP) AS last_processed,
  skill_list(k.job_skills) AS skills,
  clean_text(s.job_summary) AS summary
FROM `${DATASET}.raw_postings` p
LEFT JOIN `${DATASET}.raw_skills` k USING (job_link)
LEFT JOIN `${DATASET}.raw_summaries` s USING (job_link)
WHERE REGEXP_CONTAINS(p.job_link, r'-\d+$')
  AND tidy(p.job_title) IS NOT NULL;

CREATE OR REPLACE TABLE `${DATASET}.linkedin_postings`
OPTIONS (description = 'LinkedIn postings 2024 (Kaggle asaniczka), one row per distinct posting. Built by training/gcp/bigquery/clean.sql.')
AS
SELECT * EXCEPT (dedup_key, rn, copies), copies
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER w AS rn,
    COUNT(*) OVER (PARTITION BY dedup_key) AS copies
  FROM (
    SELECT
      *,
      FARM_FINGERPRINT(CONCAT(
        LOWER(job_title), '\x1f', LOWER(IFNULL(company, '')), '\x1f',
        IFNULL(LOWER(summary), CONCAT('loc:', LOWER(IFNULL(job_location, ''))))
      )) AS dedup_key
    FROM typed
  )
  WINDOW w AS (PARTITION BY dedup_key ORDER BY first_seen, job_link)
)
WHERE rn = 1;

CREATE OR REPLACE TABLE `${DATASET}.linkedin_posting_skills`
OPTIONS (description = 'One row per (posting, skill) from linkedin_postings. Built by training/gcp/bigquery/clean.sql.')
AS
SELECT job_link, skill
FROM `${DATASET}.linkedin_postings`, UNNEST(skills) AS skill;
