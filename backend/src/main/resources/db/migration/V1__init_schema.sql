-- Initial schema, matching the JPA entities in com.resumeanalyser.* field-for-field.
-- See docs/database-schema.md for the indicative design this was built from; this
-- version follows the entities exactly (they are the source of truth once written).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(320) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'USER',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resumes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_ref        TEXT NOT NULL,
    version         INTEGER NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, version)
);
CREATE INDEX idx_resumes_user_id ON resumes (user_id);

-- ats_* / explanation columns hold the output of the same ML /analyze-file
-- call that produced the rest of this row -- not part of the original
-- indicative schema, added so the dashboard read endpoint has something
-- durable to serve without re-calling the ML service on every page view.
CREATE TABLE parsed_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id       UUID NOT NULL UNIQUE REFERENCES resumes(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL DEFAULT '',
    email           VARCHAR(320) NOT NULL DEFAULT '',
    phone           VARCHAR(50)  NOT NULL DEFAULT '',
    skills          JSONB NOT NULL DEFAULT '[]',
    experience      JSONB NOT NULL DEFAULT '[]',
    education       JSONB NOT NULL DEFAULT '[]',
    ats_score       DOUBLE PRECISION NOT NULL DEFAULT 0,
    ats_max_score   DOUBLE PRECISION NOT NULL DEFAULT 0,
    ats_checks      JSONB NOT NULL DEFAULT '[]',
    explanation     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(255) NOT NULL UNIQUE,
    description     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE skill_vectors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id             UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    skill               VARCHAR(255) NOT NULL,
    weight              DOUBLE PRECISION NOT NULL,
    version_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    current             BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (role_id, skill, version_timestamp)
);
CREATE INDEX idx_skill_vectors_current ON skill_vectors (role_id, skill) WHERE current;

-- resume_id links a recommendation row back to the analysis run (resume upload)
-- that produced it -- not in the original indicative schema, added so the
-- dashboard read endpoint can fetch "this resume version's recommendations"
-- directly instead of guessing at a batch boundary from timestamps alone.
CREATE TABLE recommendations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    resume_id       UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    match_score     DOUBLE PRECISION NOT NULL,
    matched_skills  JSONB NOT NULL DEFAULT '[]',
    missing_skills  JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_recommendations_user_id ON recommendations (user_id, created_at DESC);
CREATE INDEX idx_recommendations_resume_id ON recommendations (resume_id);

CREATE TABLE feedback (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id           UUID NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    skill_vector_version_id     UUID REFERENCES skill_vectors(id) ON DELETE SET NULL,
    helpful                     BOOLEAN NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_feedback_recommendation_id ON feedback (recommendation_id);
