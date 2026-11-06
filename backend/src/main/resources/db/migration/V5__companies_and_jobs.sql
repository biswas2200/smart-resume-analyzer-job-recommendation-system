-- Job recommendations, step 1: the companies we read jobs from, and their
-- open postings. A company's jobs come from its own hiring tool's public job
-- feed (Lever, Greenhouse or Ashby); nothing is scraped from job boards.

CREATE TABLE companies (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(255) NOT NULL,
    -- The company's website host without "www." (e.g. "groww.in"): the
    -- de-duplication key, so "CRED" and "Cred Club" stay one company.
    domain           VARCHAR(255) NOT NULL UNIQUE,
    city             VARCHAR(64)  NOT NULL,
    -- Where we learned about it: WIKIDATA, USER (watchlist) or ADMIN.
    source           VARCHAR(16)  NOT NULL,
    wikidata_id      VARCHAR(32),
    -- PENDING (not checked yet), ACTIVE (job feed found) or UNSUPPORTED.
    status           VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    ats_provider     VARCHAR(16),
    ats_slug         VARCHAR(128),
    -- How the feed was found: CAREERS_URL, DOMAIN_SLUG or NAME_SLUG (the
    -- last is the weakest evidence; worth a look by an admin).
    detected_by      VARCHAR(16),
    last_checked_at  TIMESTAMPTZ,
    last_fetched_at  TIMESTAMPTZ,
    last_error       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_companies_status ON companies (status);

CREATE TABLE job_postings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    -- The posting's id inside its hiring tool; unique per company.
    external_id      VARCHAR(128) NOT NULL,
    title            VARCHAR(512) NOT NULL,
    location         VARCHAR(512) NOT NULL DEFAULT '',
    workplace_type   VARCHAR(32)  NOT NULL DEFAULT '',
    employment_type  VARCHAR(64)  NOT NULL DEFAULT '',
    department       VARCHAR(255) NOT NULL DEFAULT '',
    url              TEXT NOT NULL,
    apply_url        TEXT NOT NULL DEFAULT '',
    -- Plain text, kept for matching against resumes; the UI shows an excerpt
    -- and always links to the original posting.
    description      TEXT NOT NULL DEFAULT '',
    published_at     TIMESTAMPTZ,
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- False once the posting disappears from the company's feed (filled or closed).
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (company_id, external_id)
);
CREATE INDEX idx_job_postings_active_first_seen ON job_postings (active, first_seen_at DESC);
