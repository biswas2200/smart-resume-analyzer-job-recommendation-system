-- Job recommendations, step 2.

-- The company's jobs page as we last saw it linked (e.g. from the Bangalore
-- Startup Map). Kept even when its hiring tool isn't supported yet (Workday,
-- Keka), so support can be added later without finding it again.
ALTER TABLE companies ADD COLUMN careers_url TEXT;

-- The skills a posting asks for, extracted once by the ML service and
-- reused for every user's ranking. NULL = not extracted yet (new posting,
-- or its description changed).
ALTER TABLE job_postings ADD COLUMN skills JSONB;

-- A user's saved jobs and where each application stands.
CREATE TABLE saved_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_posting_id  UUID NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    -- SAVED, APPLIED, INTERVIEW, OFFER or REJECTED.
    status          VARCHAR(16) NOT NULL DEFAULT 'SAVED',
    saved_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_posting_id)
);
CREATE INDEX idx_saved_jobs_user ON saved_jobs (user_id, saved_at DESC);
