# Backend

Spring Boot 3.x on Java 21, with Spring Security (JWT), PostgreSQL, and Flyway. Owns auth,
resume upload/versioning, orchestration of the ML service, and persistence of the resulting
recommendations and feedback.

## Modules

| Module | Endpoints | Notes |
|---|---|---|
| `auth` | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Stateless JWT, bcrypt passwords, RBAC roles; `/me` reads the role fresh from the database so a role change is visible immediately. Emails in `APP_ADMIN_EMAILS` become ADMIN on register/login |
| `admin` | `GET /admin/users?email=`, `PATCH /admin/users/{id}/role` (ADMIN only) | Look an account up and set its role (`USER` / `ADMIN`); there are no tiers |
| `resume` | `POST /resumes`, `GET /resumes`, `GET /resumes/{id}/profile`, `POST /resumes/{id}/reanalyze` | Validates + stores the file (PDF or DOCX), calls the ML service's `POST /analyze-file` once per upload (five roles, AI engine for any field); `reanalyze` re-reads the stored file and re-runs it (how a result locked at upload time is recovered) |
| `recommendation` | `GET /recommendations/dashboard` | Composite read view assembled from the latest resume's persisted analysis: detected domain, ATS score, roles (or a lock with `lockReason`), explanation |
| `feedback` | `POST /feedback`, `GET /feedback/{recommendationId}` | Helpful/not-helpful verdicts (FR-10.1); triggers the skill-vector recompute once enough feedback accumulates |
| `skillvector` | `GET /roles/{roleId}/skill-vectors`, `POST /roles/{roleId}/skill-vectors/recompute` (ADMIN only) | Versioned, EMA-weighted skill store (FR-7.1-7.4) |
| `job` | `GET /jobs`, `GET /jobs/recommended`, `GET /jobs/in-demand`, `GET /jobs/saved`, `PUT`/`DELETE /jobs/{id}/saved`; `POST /admin/jobs/discover`, `/import-startup-map`, `/detect`, `/refresh`, `/reextract-skills`, `/market-demand`, `GET /admin/jobs/status`, `GET`/`POST /admin/jobs/companies` (ADMIN only) | Bengaluru companies, their open jobs (read from each company's public hiring-tool feed), jobs ranked for your resume, saved jobs. See [Jobs](#jobs) |
| `client` | — | Typed HTTP client wrapping the ML service |

## Running locally

Needs a PostgreSQL 15+ database, an S3-compatible object store (MinIO) for resume files, and
the ML service (`../ml-service/`) running.

```bash
docker compose -f ../docker-compose.yml up -d   # starts Postgres + MinIO
mvn spring-boot:run
```

Without Docker, point `DB_URL`/`DB_USERNAME`/`DB_PASSWORD` at an existing PostgreSQL database
and `OBJECT_STORAGE_*` at an existing S3-compatible endpoint instead.

Flyway (`src/main/resources/db/migration/`) creates the schema on startup; Hibernate only
validates it matches the entities (`ddl-auto: validate`), it never generates DDL itself.

## API docs

Swagger UI: `http://localhost:8080/swagger-ui/index.html` — browse every endpoint and try
requests directly. Public/login endpoints work with no setup; for anything else, call
`POST /auth/login`, copy the `token` from the response, and paste it into the Authorize button
(top right) as `<token>` (no `Bearer ` prefix needed, Swagger adds it). Raw OpenAPI document at
`http://localhost:8080/v3/api-docs`.

Key environment variables (see `src/main/resources/application.yml` for every default):

| Variable | Default | Purpose |
|---|---|---|
| `DB_URL` / `DB_USERNAME` / `DB_PASSWORD` | `jdbc:postgresql://localhost:5432/resume_analyser` / `postgres` / `postgres` | Database connection |
| `JWT_SECRET` | dev-only default | HS256 signing key — **must** be overridden in any real deployment |
| `ML_SERVICE_BASE_URL` | `http://localhost:8000` | Where the ML service is running |
| `OBJECT_STORAGE_ENDPOINT` | `http://localhost:9010` | MinIO/S3-compatible endpoint resume files are stored in (host port shifted off MinIO's default 9000, which commonly collides with other local tools) |
| `OBJECT_STORAGE_ACCESS_KEY` / `OBJECT_STORAGE_SECRET_KEY` | `minioadmin` / `minioadmin` | Object storage credentials |
| `OBJECT_STORAGE_BUCKET` | `resumes` | Bucket resume files are stored in (created on startup if missing) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:4200` | Origin(s) the frontend is served from |
| `APP_ADMIN_EMAILS` | *(empty)* | Comma-separated emails promoted to ADMIN on register/login — the bootstrap for the first administrator |

## Jobs

Job recommendations, step 1: which companies we follow and their open jobs in Bengaluru.

- **Companies.** `POST /admin/jobs/discover` adds every company Wikidata lists with its head office in Bengaluru and a website (322 on 22 Oct 2026; newspapers, parties and charities are left out), then looks for each one's job feed. `POST /admin/jobs/companies` adds one company by hand (`name`, `website`, optional `careersUrl`); the watchlist's `POST /watchlist/companies` uses the same path. Companies are keyed by website domain, so the same company is never added twice.
- **Finding a feed** (`AtsDetector`). Only the hiring tools' own public feeds are asked, never a company's website: a careers link that already points at Lever, Greenhouse or Ashby is read directly; otherwise each tool is asked for a board named after the website (`groww.in` → `groww`), then after the company name. A guessed board (website or name) must have at least one job in India, or it is taken to be another company's board: the first run matched "The Better India" to Lever's `better` and via.com to Greenhouse's `via`. `detected_by` records how each feed was found. First run (22 Oct 2026): 322 companies, 6 with a feed (BarRaiser, CRED, Groww, InMobi, Meesho, Sarvam AI), 150 open Bengaluru jobs.
- **Jobs.** Each feed is read whole and only postings whose location names Bengaluru or Bangalore are stored. A posting that leaves the feed is kept with `active = false`. `POST /admin/jobs/refresh` re-reads every feed; it also runs daily at 06:30 India time (`JOBS_REFRESH_CRON`, `-` to turn off). On Cloud Run, where an idle instance may be stopped, a Cloud Scheduler call to the refresh endpoint is the reliable trigger.
- **Bangalore Startup Map.** `POST /admin/jobs/import-startup-map` reads the map's public sitemap and each company page's schema.org data (name, website) and its Apply links, one page a second (`JOBS_PAGE_DELAY`). Its `/api/` is never called: its robots.txt asks crawlers to keep out. An Apply link on Lever, Greenhouse or Ashby is read at once; another tool (Workday, Keka) is recorded in `careers_url` as not supported yet. Permission to use the list was requested on 22 Oct 2026; the app credits the map.
- **Skills and ranking.** After every task, the ML service's `POST /extract-job-skills` fills in each new or changed posting's `skills` once. Job-ad copy (soft skills, perks, footer links such as "Communication", "Yoga", "Instagram") is left out. After the extractor changes, `POST /admin/jobs/reextract-skills` re-reads every job. `GET /jobs/recommended?q=&workplace=&limit=` (each word of `q` must start a word of the title or company name) sends the latest resume's skills and its top 3 role matches, with every open job's stored skills, to `POST /rank-jobs`: score = 0.45 × skills covered (scaled down for a job naming fewer than 5 skills) + 0.30 × meaning similarity + 0.25 × title-to-role fit (0.5 × title fit when a job's skills can't be read), each job with its matched and missing skills and a one-line reason. Without a resume, jobs come newest first.
- **Market demand (EMA).** After each daily refresh (or `POST /admin/jobs/market-demand`), the ML service's `POST /market-demand` assigns each open job to the catalogue role its title is closest to (similarity at least 0.6, abbreviations such as SDE spelled out) and, for roles with at least 3 jobs, measures the share of jobs asking for each skill. That share becomes each catalogue skill's EMA signal (`SkillVectorService`, α = 0.3; 0.5 for a skill no job asked for), the demand is stored in `market_skill_demand`, and the new weights snapshot is pushed to the ML service (`PUT /weights-snapshot`), which uses it for role matching. `GET /jobs/in-demand` shows a user the most-asked skills for their top 3 roles, marking the ones their resume has. First run (22 Oct 2026): 489 jobs, 43 roles, 392 weights updated.
- **Saved jobs.** `PUT /jobs/{id}/saved` saves a job or sets its status (SAVED, APPLIED, INTERVIEW, OFFER, REJECTED); `DELETE` removes it; `GET /jobs/saved` lists them, a closed job marked `active: false`.
- **Watchlist.** `GET /watchlist`, `GET /watchlist/companies?q=`, `PUT` and `DELETE /watchlist/{companyId}`. `POST /watchlist/companies` (`name`, `website`, optional `careersUrl`) watches a company that is not in our list yet: it reuses a company with the same domain, or adds one (source `USER`) and looks for its Lever, Greenhouse or Ashby board straight away; it answers 201, or 400 for a website that is not a web address. It counts as one change and checks the cap before any job-board call. Detection only calls those three job boards, never the website itself. Limits are the same for every user and tier (`app.watchlist.*`): at most 25 companies (`WATCHLIST_MAX_COMPANIES`; adding one more answers 409 with the reason), and at most 10 watch / stop-watching requests a minute and 60 an hour (`WATCHLIST_CHANGES_PER_MINUTE`, `WATCHLIST_CHANGES_PER_HOUR`; going faster answers 429 with `Retry-After`). `GET /watchlist/limits` returns the limits and how many companies the user watches. The change counts are kept in memory per backend instance (`WatchlistRateLimiter`); with several instances each counts on its own, and a shared store such as Redis would be the next step.
- **Politeness.** One task at a time, a pause between requests (`JOBS_REQUEST_DELAY`, 150 ms), and a `User-Agent` naming the app (`JOBS_USER_AGENT`; add a contact before running in production, as Wikidata asks).

| Feed | Endpoint |
|---|---|
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}` |

## Logging

`common.logging.RequestIdFilter` gives each request an id (an incoming
`X-Request-Id` when it is safe, otherwise a new UUID), returns it in the
response header, adds it to every log line (`[id]` after the level) and passes
it to the ML service, whose logs carry the same id. One access line per request
(method, path, status, duration), one line per ML-service call, one outcome
line per resume analysis, and `LoggingAspect`'s per-method timings. A 500's
`traceId` is the request id. Bodies, tokens, passwords and resume content are
never logged.

`LOG_LEVEL` (app packages, default `INFO`), `LOG_LEVEL_ROOT` and `LOG_FILE`
(e.g. `logs/backend.log`) are environment variables.

## Testing

```bash
mvn test
```
