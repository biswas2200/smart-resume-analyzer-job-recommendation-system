-- Job-market demand: for each catalogue role, the share of its open
-- Bengaluru jobs that ask for each skill, as of the last daily update.
-- Replaced whole on every update; the EMA weights in skill_vectors keep the
-- history (FR-7.4).
CREATE TABLE market_skill_demand (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_title   VARCHAR(255) NOT NULL,
    skill        VARCHAR(255) NOT NULL,
    share        DOUBLE PRECISION NOT NULL,
    -- How many open jobs the role had (the same on every row of a role).
    job_count    INTEGER NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (role_title, skill)
);
CREATE INDEX idx_market_skill_demand_role ON market_skill_demand (role_title, share DESC);
