-- What the Bangalore Startup Map says about a company, for the company cards' filters and labels.
-- Facts only (no descriptions): sector, neighbourhood, funding stage, team-size band, founding
-- year and tags. Filled by POST /admin/jobs/companies/facts, matched on companies.domain.
ALTER TABLE companies
    ADD COLUMN sector        VARCHAR(32),
    ADD COLUMN area          VARCHAR(64),
    ADD COLUMN funding_stage VARCHAR(32),
    ADD COLUMN team_size     VARCHAR(16),
    ADD COLUMN founded       INTEGER,
    ADD COLUMN tags          VARCHAR(255);
CREATE INDEX idx_companies_sector ON companies (sector);
