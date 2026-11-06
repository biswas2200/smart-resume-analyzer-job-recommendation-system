-- Company watchlist, step 1: the companies a user follows for new jobs.
-- V7 is taken by the job-market-demand branch.

CREATE TABLE watched_companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, company_id)
);
CREATE INDEX idx_watched_companies_user ON watched_companies (user_id, added_at DESC);
