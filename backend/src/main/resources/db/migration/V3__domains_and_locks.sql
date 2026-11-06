-- Career OS: every resume is classified into a job domain (ml-service
-- domain_classifier.py, deterministic), and each domain is served by an engine
-- (local / llm) and requires a tier (free / premium) per domains.json. The
-- analysis records what was detected and whether recommendations were locked
-- because a Premium-only domain was analysed at the free tier; roles record
-- which domain's catalogue they belong to. Existing rows all predate domains
-- and were produced by the engineering-only engine, hence the defaults.
ALTER TABLE parsed_profiles
    ADD COLUMN domain                 VARCHAR(64)      NOT NULL DEFAULT 'engineering',
    ADD COLUMN domain_name            VARCHAR(255)     NOT NULL DEFAULT '',
    ADD COLUMN domain_confidence      DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN domain_engine          VARCHAR(16)      NOT NULL DEFAULT 'local',
    ADD COLUMN domain_tier            VARCHAR(16)      NOT NULL DEFAULT 'free',
    ADD COLUMN recommendations_locked BOOLEAN          NOT NULL DEFAULT false,
    ADD COLUMN lock_reason            VARCHAR(64);

ALTER TABLE roles
    ADD COLUMN domain VARCHAR(64) NOT NULL DEFAULT 'engineering';

CREATE INDEX idx_roles_domain ON roles (domain);
