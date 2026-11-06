-- One version of the product: the Free/Premium split is gone, so the
-- per-account AI allowance counters, the per-analysis domain tier and the
-- PREMIUM_USER role go with it.
ALTER TABLE users DROP COLUMN ai_period, DROP COLUMN ai_analyses_used;
ALTER TABLE parsed_profiles DROP COLUMN domain_tier;
UPDATE users SET role = 'USER' WHERE role = 'PREMIUM_USER';
-- "ai_engine_required" meant "the monthly allowance is spent"; that limit no
-- longer exists, so those analyses are simply re-run by "re-analyse".
