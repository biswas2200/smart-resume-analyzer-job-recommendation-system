-- Records which explainer backend produced parsed_profiles.explanation
-- (FR-5.4/FR-12.2): 'template' (deterministic, default) or 'llm' (Premium
-- narrative, or a fallback to 'template' if the LLM call failed -- NFR-3.1).
-- Existing rows predate this distinction and were all produced by the LLM
-- backend (the only one that existed before this migration), so the ADD
-- COLUMN default backfills them to 'llm'; new rows always set this column
-- explicitly, but the column's own default is switched to 'template'
-- afterward to match the app's new default backend.
ALTER TABLE parsed_profiles ADD COLUMN explanation_source VARCHAR(20) NOT NULL DEFAULT 'llm';
ALTER TABLE parsed_profiles ALTER COLUMN explanation_source SET DEFAULT 'template';
