# Software Requirements Specification (SRS)

> Project: Smart Resume Analyser and Job Recommendation System
> Document version: 2.0 · Date: 2026-09-10 · Status: Active; supersedes v1.0 (2026-08-28)
> Prepared by: Amitosh Biswas and development team, MCA, Nitte Meenakshi Institute of Technology (NMIT), Bengaluru

This is the markdown successor of the v1.0 Word document. Section numbering and every `FR-x.y` / `NFR-x.y` identifier from v1.0 are preserved because the rest of this documentation set cites them; new requirements are appended with new ids. Changes from v1.0 are listed in Appendix C.


## 1. Introduction

### 1.1 Purpose
This SRS defines the functional and non-functional requirements for Smart Resume Analyser and Job Recommendation System ("the System"). It is the authoritative reference for design, implementation, and testing, and a supporting document for academic evaluation. v2.0 extends v1.0 with the cloud web app on Google Cloud Platform, the result-parity/determinism guarantee, and the cloud model training and release process. The standalone offline self-hosted distribution is archived in [`docs/archive/community-edition.md`](archive/community-edition.md).

### 1.2 Scope
The System is a candidate-facing resume analyser delivered as one cloud web app hosted on Google Cloud Platform (GCP), with the same product for every account:

| Delivery | Who it is for |
|---|---|
| Cloud web app | Hosted web app on GCP with accounts and full history. Candidates who want fast, deterministic analysis without installing anything, AI support across all 23 domains, LLM coaching narratives and job-description matching |

The System:

- Accepts resume uploads (PDF today; DOCX planned) and extracts a structured candidate profile using a local NER model for engineering, with no LLM and no network call.
- Normalizes extracted skills against a canonical skill taxonomy.
- Recommends career roles using embedding-based similarity matching against a curated job-role dataset. This is a deterministic process, not LLM reasoning.
- Identifies skill gaps between a candidate's profile and target roles.
- Scores ATS compatibility with a rule-based rubric.
- Generates an explanation of the results: an LLM-written coaching narrative, with a deterministic template as the fallback. The LLM never influences a score.
- Updates its skill-role weights over time with an exponential-moving-average (EMA) mechanism informed by user feedback and job-market data (both implemented; market data since v2.12), and publishes those weights as versioned snapshots.
- Guarantees deterministic, reproducible results for the same input and the same engine version (§3.11).

Out of scope for the current release: automated job-application submission, direct integration with employer ATS platforms, multi-language resumes, scanned-image resumes.

### 1.3 Definitions, acronyms and abbreviations

| Term | Definition |
|---|---|
| ATS | Applicant Tracking System: employer software used to screen resumes. |
| Core engine | The versioned, deterministic pipeline artifact (models + taxonomy + weights snapshot + code) shared by all editions (§3.11). |
| EMA | Exponential Moving Average: time-decayed weighted averaging used to update skill-vector weights. |
| Engine fingerprint | The tuple `{engine_version, ner_model_sha, embed_model_sha, taxonomy_sha, weights_snapshot_id}` returned with every analysis (FR-11.2). |
| ESCO | European Skills, Competences, Qualifications and Occupations taxonomy (free for commercial reuse). |
| JD | Job Description. |
| JWT | JSON Web Token, used for stateless authentication. |
| LLM | Large Language Model. |
| MVP | Minimum Viable Product. |
| NER | Named Entity Recognition: the local model that extracts name, skills, degrees, titles from resume text. |
| ONNX | Open Neural Network Exchange: the portable model format the core engine ships. |
| REST | Representational State Transfer, an API architectural style. |
| SRS | Software Requirements Specification (this document). |
| Weights snapshot | A frozen, hashed export of the current EMA skill weights, published per release (FR-7.5). |

### 1.4 References
- Comparable system: "An AI-Driven Resume Analyser with Job Recommender and Portfolio Code Generator", IJRASET, April 2026. It identifies static cosine-similarity matching as a limitation, which this System addresses.
- Market context: Mordor Intelligence, "AI Resume Screening and Matching Market — Size & Growth Trends", 2026.
- Edition and parity precedents: SonarQube Community vs Cloud; Semgrep Community vs Pro; Plane Community vs Commercial; [Editions & Parity](editions-and-parity.md) has the full research table.
- Regulatory context: EU AI Act, Annex III point 4 (employment), high-risk obligations applicable from 2 August 2026.
- Internal: [Editions & Parity](editions-and-parity.md), [Datasets](datasets.md), [Architecture](architecture.md), [LLD](lld.md).

### 1.5 Document overview
Section 2 describes the product at a high level. Section 3 specifies functional requirements per feature (3.1 to 3.10 from v1.0; 3.11 to 3.13 new). Section 4 covers external interfaces, now including hardware requirements for Community Edition. Section 5 specifies non-functional requirements. Section 6 summarizes the architecture. Section 7 outlines data requirements. Section 8 covers licensing and contribution. Appendices provide a glossary, a feature priority matrix, and revision history.


## 2. Overall description

### 2.1 Product perspective
The System is a standalone application positioned against two categories:

- Recruiter-facing AI screening platforms (HireVue, Eightfold AI, iCIMS) serve employers, not candidates.
- Open-source resume tools (e.g. Resume-Matcher, Reactive Resume, OpenResume) are self-hostable but either make their score depend on whichever LLM the user configured, so two users cannot compare results. The System's answer is a deterministic core engine shared by a self-hosted edition and a hosted product, with provable result parity between them.

### 2.2 Product functions
A user can:

1. Upload a resume and receive a structured, parsed profile.
2. Receive ranked career-role recommendations with a numeric match score.
3. See a skill-gap breakdown and guidance for each recommended role.
4. Paste a specific job description and receive a targeted match score.
5. Receive an ATS compatibility score with a breakdown of contributing factors.
6. Provide feedback on recommendations, which feeds the EMA weights.
7. Run the entire pipeline offline on their own machine (Community Edition) and verify, via the engine fingerprint, that it is the same engine the web app runs.
8. Receive an LLM-written coaching narrative and keep unlimited history.

### 2.3 User classes and characteristics

| User class | Characteristics |
|---|---|
| Candidate (primary) | Job-seeking fresher or early-career professional (0 to 2 years). Comfortable with web apps; no technical background assumed. |
| Self-hosting user, Community Edition | Runs the Docker image locally; may be a candidate, a placement cell, or a developer. Needs Docker and the minimum PC spec in §4.2. |
| System Administrator / Development Team | Maintains taxonomy and role dataset, publishes weights snapshots and model releases, monitors health. |
| Institution / Placement Cell (future) | Batch analysis of many candidates against one role (Appendix B, stretch). |

### 2.4 Operating environment

| Component | Technology |
|---|---|
| Backend | Java 21, Spring Boot 3.3, Spring Security (JWT), Flyway, springdoc-openapi |
| ML service / core engine | Python 3.12, FastAPI, ONNX Runtime (CPU) with PyTorch CPU fallback, sentence-transformers, transformers, pdfplumber |
| Database | PostgreSQL 15+ |
| Object storage | MinIO (S3-compatible) for uploaded resume files |
| Frontend | HTML5, one hand-written CSS file (light and dark themes, no CSS framework), vanilla JavaScript (ES modules, no build step); tests via `node --test` |
| LLM provider (AI-engine / opt-in only) | Gemini on Vertex AI (`gemini-2.5-flash-lite` by default; `gemini-2.5-flash` optional) authenticated with Google Application Default Credentials (no API key); Groq (`llama-3.3-70b-versatile`) optional via `LLM_PROVIDER=groq` |
| Community Edition packaging | Docker multi-arch image (`linux/amd64`, `linux/arm64`), models and vector tables baked in, no runtime network |
| Web deployment | Single Linux VM running Docker Compose (ml-service, backend, PostgreSQL, MinIO); demo target Hetzner CX23-class or GCP e2-medium-class |

### 2.5 Design and implementation constraints

1. Core matching and scoring logic must be deterministic and explainable; LLM usage is restricted to explanation and opt-in extraction (§3.3, §3.5).
2. The core engine must run with no network access and no API key (Community Edition requirement, NFR-3.2).
3. Every model on the score path must be pinned by content hash and shipped inside the release artifact; nothing on the score path may be downloaded at runtime (§3.11).
4. Community Edition must meet the minimum PC specification in §4.2.
5. All source code is governed by a proprietary, all-rights-reserved license (§8); the licence of the published Community image is an open decision (§8.1).
6. Demonstration deployment is constrained to a single low-cost VM.

### 2.6 Assumptions and dependencies

- Uploaded resumes are digitally generated, text-extractable PDFs; scanned images are out of scope.
- Training datasets listed in [Datasets](datasets.md) remain available under their stated licences.
- Groq/Gemini remain available within free or low-cost limits for explanation generation; their unavailability must never affect a score (NFR-3.1).
- The initial role/skill dataset is manually curated; migration to ESCO is planned (§3.13).


## 3. System features (functional requirements)

Each feature carries a priority (Urgent / High / Medium / Low) and numbered requirements using "The system shall…". Status tags: [Implemented], [Planned].

### 3.1 Resume upload and parsing
Priority: High

- FR-1.1 The system shall allow users to upload resume files in PDF format up to 5 MB. [Implemented] DOCX support [Planned].
- FR-1.2 The system shall extract candidate name, contact information, education, work experience, and skills from the uploaded resume using a local NER model by default; an LLM-based extraction path shall remain available as an explicit opt-in (`PARSER_BACKEND=llm`). *(v1.0 said "LLM-based extraction"; changed.)* [Implemented]
- FR-1.3 The system shall reject and report a clear error for unsupported file formats or files exceeding the size limit. [Implemented]
- FR-1.4 The system shall store the parsed structured profile associated with the user's account (web editions). [Implemented]
- FR-1.5 The system shall retain each new upload as a distinct, timestamped version rather than overwriting the previous one. [Implemented]
- FR-1.6 The system shall segment resume text into sections (Skills, Experience, Education, other) by heading detection before running the NER model, and shall run the NER model only on the Experience and Education sections. [Implemented] (`sectioner.py`; falls back to running NER over the whole text when no heading is recognized)
- FR-1.7 The system shall extract skills by deterministic dictionary matching against the canonical taxonomy over the whole text, merging in NER-detected skill spans for recall. [Implemented] (`dictionary_skills.py`; token-based whole-text matching, not literally Aho-Corasick; see the module's docstring)

### 3.2 Skill normalization
Priority: High

- FR-2.1 The system shall map extracted raw skill strings to a canonical skill taxonomy (e.g., "ReactJS", "React.js" → "React"). [Implemented]
- FR-2.2 The system shall flag extracted skills that cannot be matched to the canonical taxonomy for manual review. [Planned]
- FR-2.3 The taxonomy shall be extensible by an administrator without requiring a code deployment. [Planned]

### 3.3 Career recommendation engine
Priority: Urgent (the System's core differentiator).

- FR-3.1 The system shall generate a vector embedding for each candidate's normalized skill profile using a sentence-transformer model. [Implemented]
- FR-3.2 The system shall compute cosine similarity between the candidate's skill-profile vector and each job role's weighted skill vector, using the weights snapshot in effect for the engine version. [Implemented] (`matcher.py` + `weights.py`; weight defaults to 1.0 per skill until an admin exports a snapshot via `GET /roles/skill-vectors/snapshot`)
- FR-3.3 The system shall return a ranked list of the top N (default N = 5) recommended roles, each with a numeric match score. [Implemented]
- FR-3.4 The system shall recompute a candidate's recommendations whenever a new resume version is uploaded. [Implemented]
- FR-3.5 The system shall round every match score to two decimal places before ranking and shall break ties deterministically by role identifier, so that ranking is stable across CPU architectures. [Implemented]
- FR-3.6 The system shall precompute the embedding of every canonical skill and every role at build time and ship them as a hashed lookup table; at runtime the embedding model shall be invoked only for skills absent from the taxonomy. [Planned] (needs a real embedding-model run against the full taxonomy)

### 3.4 Skill gap analysis
Priority: High

- FR-4.1 The system shall compute the set of skills present in a target role's profile but absent from the candidate's normalized skill set. [Implemented]
- FR-4.2 The system shall rank identified gaps by the skill's weighted importance to the target role. [Planned]
- FR-4.3 The system shall present gap results alongside each recommended role. [Implemented]

### 3.5 Explanation generation
Priority: Medium. This explains results that were already computed deterministically; it never generates the results themselves.

- FR-5.1 The system shall generate an explanation of why a role was recommended, grounded in the computed match score and matched skills. [Implemented] (both backends)
- FR-5.2 The system shall generate coaching-style guidance on addressing identified skill gaps, without rewriting or fabricating resume content. [Implemented] (both backends)
- FR-5.3 Explanation generation shall not influence the underlying match score or ranking. [Implemented]
- FR-5.4 The explanation shall be an LLM-written coaching narrative labelled as non-deterministic, produced by Gemini on Vertex AI; when the AI engine is unavailable it shall fall back to a deterministic template from the matched/missing skills and ATS breakdown, requiring no network access. [Implemented] (`explain_results` backend `llm` with template fallback; every response carries `explanation_source`)

### 3.6 Results dashboard
Priority: High

- FR-6.1 The system shall display the parsed profile, recommended roles, match scores, and skill gaps in a single consolidated view. [Implemented]
- FR-6.2 The system shall allow users to view their resume version history and match-score trend (every version is kept). [Implemented] (match-score trend view not yet a distinct UI)
- FR-6.3 The dashboard shall be usable on desktop and mobile viewport sizes. [Implemented]

### 3.7 Temporal skill-vector update mechanism
Priority: Urgent

- FR-7.1 The system shall store each role's skill-weight vector with a version timestamp. [Implemented]
- FR-7.2 The system shall update skill weights with `new_weight = α × new_signal + (1 − α) × old_weight`, α configurable (`app.skill-vector.alpha`, default 0.3). [Implemented]
- FR-7.3 The system shall record each user's "helpful / not helpful" feedback and incorporate it into the EMA update as a weighted signal once a configurable threshold of feedback is reached. [Implemented]
- FR-7.4 The system shall preserve prior weight-vector versions for auditability and trend reporting. [Implemented]
- FR-7.5 The system shall export the current weights as a versioned, hashed snapshot (`{snapshot_id, created_at, weights}`) via an administrator endpoint; the core engine shall accept such a snapshot as its weights source, defaulting to uniform weights when none is supplied. [Implemented] (`GET /roles/skill-vectors/snapshot`, `weights.py`; nothing yet automates writing the export into `ml-service/app/data/weights_snapshot.json`, so an operator does that step by hand today)
- FR-7.6 The system shall measure, daily, the share of each catalogue role's open jobs that ask for each skill, use it as that role's EMA signal (0.5 + 0.5 × share ÷ the role's most-asked share, so an unasked skill fades towards half weight, never to zero), install the updated weights in the core engine, and show users the most-asked skills for their top roles. [Implemented (v2.12)]: `ml-service/app/services/market_demand.py`, `POST /admin/jobs/market-demand`, `GET /jobs/in-demand`, `PUT /weights-snapshot`.

### 3.8 Job description (JD) matching
Priority: Medium

- FR-8.1 The system shall allow a user to paste a job description as free text (up to 20,000 characters). [Implemented (v2.3)]: `POST /resumes/{id}/jd-match`, the dashboard's "JD match" tab, available to every account.
- FR-8.2 The system shall compute a match score and list matched and missing skills between the candidate's stored profile and the pasted JD, deterministically and without an LLM: JD skills are dictionary matches against both taxonomies, `score = 0.6 × coverage + 0.4 × embedding similarity` (2 dp), plus the catalogue role the JD most resembles (`ml-service/app/services/jd_match.py`). Nothing is persisted. [Implemented (v2.3), Premium]

### 3.9 ATS compatibility score
Priority: Medium. Fully deterministic and rule-based, with no model involved.

- FR-9.1 The system shall check for standard section headers (Experience, Education, Skills). [Implemented]
- FR-9.2 The system shall flag formatting elements known to break ATS parsers (tables, images, multi-column layouts). [Planned]
- FR-9.3 The system shall compute a keyword-coverage score against target keywords when provided. [Implemented]
- FR-9.4 The system shall present the ATS score with a plain-language breakdown of contributing factors. [Implemented]

### 3.10 Feedback collection
Priority: Medium

- FR-10.1 The system shall allow a user to mark a recommendation as "helpful" or "not helpful". [Implemented]
- FR-10.2 Feedback shall be persisted and linked to the specific recommendation and the skill-vector version active at the time. [Implemented]

### 3.11 Core engine architecture and result parity *(revised in v2.2)*
Priority: Urgent (the product's central promise).

- FR-11.1 The system shall be built around one core engine artifact (parser, sectioner, dictionary skills, NER model, embedding model or vector table, taxonomy, weights snapshot, ATS rules, template explainer) that is byte-identical across environments for a given release tag. [Planned]
- FR-11.2 Every analysis response shall include an `engine_fingerprint` containing the engine version and the content hashes of the NER model, embedding model or vector table, taxonomy, and weights snapshot. `GET /health` shall return the same fingerprint. [Implemented (mechanism); real model-weight hashing planned] `taxonomy_sha` hashes the real bundled taxonomy file; `ner_model_sha`/`embed_model_sha` hash the configured model identifier, not yet the downloaded weights themselves (needs the ONNX pinning step in §3.11's implementation).
- FR-11.3 For identical input and identical `engine_fingerprint`, the core engine shall return identical `profile`, `ats_score`, `matches` (scores and order), and `gaps` across any supported CPU architecture. [Planned]
- FR-11.4 The AI-written narrative and any other additions shall never alter the base score computed by the core engine; they add information as separate, labelled fields. Where live weights are used, the response shall disclose that the weights differ from the published snapshot. [Planned]
- FR-11.5 The core engine shall be deployable as containerized microservices on Google Cloud Platform (Compute Engine VM / Cloud Run) and locally via Docker Compose for development and testing. The standalone offline CLI distribution is archived in [`docs/archive/community-edition.md`](archive/community-edition.md). [Implemented for Compose; GCP deployment planned]
- FR-11.6 A release shall be blocked unless a golden test suite executed against the engine API produces verified outputs and identical fingerprints. [Planned]

### 3.12 Roles and the AI engine *(revised in v2.14: one version of the product)*
Priority: High

- FR-12.1 The system shall maintain user roles `USER` and `ADMIN` and read the role from the database on every request. [Implemented]
- FR-12.2 Every account shall receive the same product: five role matches, the AI-written explanation, JD match, unlimited analyses and every resume version. Roles control administration only. [Implemented]
- FR-12.3 Role checks shall be declared on the owning module's controller methods with method security, not in a central URL list. [Implemented]
- FR-12.4 The frontend shall show no plans, tiers or upgrade prompts; the only role-dependent element is the administrator badge. [Implemented]
- FR-12.5 The following shall require `ADMIN`: recompute skill vectors, export a weights snapshot, publish a model release, change an account's role. [Implemented (recompute, snapshot export, role change via `PATCH /admin/users/{id}/role`); model release planned], since the model-release process itself (§3.13) doesn't exist yet.
- FR-12.6 *(new in v2.1, revised v2.15)* Every resume shall be classified into one job domain (`domains.json`) deterministically and without an LLM, from its headline and opening (without the education block) compared with the catalogue's roles, plus dictionary evidence; each domain declares the engine that reads it (`local` / `llm`). All domains are `local`: the NER model and dictionaries extract the profile, and the LLM only writes the narrative. A domain set to `llm` (opt-in) that cannot use the AI engine shall still return the ATS score, domain and profile card, with `recommendations_locked = true` and a `lock_reason` of `community_edition` or `ai_budget_exhausted`, and shall make no LLM call. [Implemented]
- FR-12.7 *(new in v2.1)* A user shall be able to re-analyse an existing resume version (`POST /resumes/{id}/reanalyze`) without re-uploading, so a result that was locked at upload time can be recovered. [Implemented]
- FR-12.8 *(new in v2.1)* Accounts whose email is listed in `APP_ADMIN_EMAILS` shall become `ADMIN` on registration or login (bootstrap); an administrator can change another account's role with `PATCH /admin/users/{id}/role`. [Implemented]
- FR-12.9 *(revised v2.14)* The operator may cap AI spend with `LLM_DAILY_BUDGET_USD` (estimated USD per UTC day, default 0 = off). Past the cap, requests that need the AI engine lock with `ai_budget_exhausted` until the next UTC day; local-engine analyses are never affected. No per-account allowance exists. [Implemented]
- FR-12.10 *(new in v2.2)* For headless or local testing environments with `LLM_PROVIDER=none`, the service shall build no LLM client, serve Engineering & Technology in full, and return `lock_reason = community_edition` for other domains. In cloud deployments, `LLM_PROVIDER=gemini` connects to Vertex AI. [Implemented]

### 3.13 Model training and release *(new in v2.0, revised v2.2)*
Priority: High

- FR-13.1 The repository shall contain a cloud-based training pipeline (`ml-service/training/`) executable on GCP compute resources (e.g. GPU VM / Vertex AI Workbench) for (a) the resume NER model, including distillation into a smaller student, and (b) the skill/role embedding model, with datasets and licences recorded in `DATASETS.md` (see [Datasets](datasets.md)). Labels for unlabelled public resume corpora are produced offline by `gemini-3.5-flash-lite` on Vertex AI (Application Default Credentials), never from user resumes (NFR-7.1); see `ml-service/training/data_prep/LABELLING.md`. [Planned; data preparation and labelling tooling implemented]
- FR-13.2 Trained models shall be exported to ONNX, content-hashed, and referenced by hash from the core engine configuration; the runtime image shall never carry training dependencies. [Planned]
- FR-13.3 A new model shall be released only if held-out entity-level F1 (NER) or ranking quality (embedder) is not below the previous release, the golden suite (FR-11.6) is regenerated and reviewed, and the rank correlation with the previous release is reported in the release notes. [Planned]
- FR-13.4 User feedback and corrections from the web editions may be used as training data only with explicit, revocable consent, and shall be anonymized before storage in the training corpus. [Planned]
- FR-13.5 The cloud web app shall receive one model release; no deployment shall ship an unverified model or a different numeric precision than another. [Planned]


## 4. External interface requirements

### 4.1 User interfaces

| Screen | Purpose |
|---|---|
| Upload | Resume upload with format/size validation |
| Dashboard | Profile, recommendations, match scores, gaps (FR-6.1) |
| JD Match | Free-text JD input and targeted result (§3.8) |
| ATS Score | Breakdown of ATS factors (§3.9) |
| Feedback controls | Helpful / not helpful on each recommendation |

### 4.2 Hardware and cloud deployment targets (Google Cloud Platform)

The application stack and training workloads are hosted on Google Cloud Platform (GCP):

| Deployment type | Target GCP specification | Purpose |
|---|---|---|
| App stack host (Option A) | Compute Engine `e2-standard-4` (4 vCPU, 16 GB RAM, 30 GB SSD) | Runs Docker Compose: Frontend, Backend, ML Service, PostgreSQL, and MinIO |
| Model training and fine-tuning | Compute Engine / Vertex AI Workbench with NVIDIA T4 GPU (16 GB VRAM) | Executes offline NER continue-training, distillation, and SentenceTransformer fine-tuning |
| Serverless option (planned hybrid) | Cloud Run (2 vCPU, 2 GB RAM per instance) + Cloud SQL | Serverless hosting for ML service and backend container images |

### 4.3 Software interfaces

| System | Interface |
|---|---|
| Google Vertex AI (Gemini 2.5 Flash Lite) | HTTPS/REST via Google ADC. Coaching narrative only (extraction for any domain is opt-in). Never on the score path. |
| ONNX Runtime / PyTorch CPU | In-process inference for NER and (fallback) embedding. |
| sentence-transformers / transformers | In-process, build-time vector precomputation and training. |
| PostgreSQL | JDBC from the backend; Flyway migrations. |
| MinIO / S3 | Resume file storage from the backend. |
| Docker & Docker Compose | Container packaging and deployment on GCP VM. |
| GitHub REST API | Development tooling only. |

### 4.4 Communication interfaces
- Frontend ↔ Backend: REST over HTTPS, JSON.
- Backend ↔ ML Service: REST over HTTP (internal network), JSON; the backend sends the file and the number of roles wanted.
- Authentication: JWT bearer tokens issued by the backend.


## 5. Non-functional requirements

### 5.1 Performance
- NFR-1.1 Resume parsing shall complete within 15 seconds for a file up to 5 MB on the web deployment.
- NFR-1.2 Recommendation computation against up to 100 roles shall complete within 2 seconds.
- NFR-1.3 *(revised)* The core engine shall analyse a two-page resume in ≤ 3 seconds end to end on the GCP standard specification in §4.2, with peak RSS ≤ 1.5 GB.

### 5.2 Security
- NFR-2.1 JWT sessions with a maximum lifetime of 24 hours.
- NFR-2.2 Passwords stored with a salted one-way hash (bcrypt); never persisted or logged in plaintext.
- NFR-2.3 All client-server communication over HTTPS/TLS.
- NFR-2.4 API keys and credentials only in environment variables or secrets; never committed.
- NFR-2.5 *(new in v2.11)* Uploaded resume content is untrusted input. Text a reader cannot see (white, tiny or off-page text in a PDF; hidden, tiny or white runs in a DOCX, from v2.13) is left out of the analysis and fails an ATS check; resume text sent to an LLM is delimited and declared to be data, never instructions; skills an LLM extracts are kept only if the resume text mentions them; and parsed profile fields are length-capped below the database column sizes. Scores and matches are never produced by an LLM. [Implemented]

### 5.3 Reliability and availability
- NFR-3.1 If the LLM API is unavailable, the system shall return deterministic scores with the template explanation rather than failing the request.
- NFR-3.2 *(revised)* The core deterministic engine shall compute scores and matches independently of third-party LLM API availability.

### 5.4 Scalability
- NFR-4.1 The backend shall be stateless where feasible to allow horizontal scaling.

### 5.5 Maintainability
- NFR-5.1 Deterministic matching/scoring logic and LLM-invocation logic shall be separable, independently testable modules.
- NFR-5.2 Training code (`ml-service/training/`) and runtime code shall have separate dependency sets; the runtime container shall not include training dependencies.

### 5.6 Usability
- NFR-6.1 A first-time user shall reach a recommendation within three actions (upload, confirm, view).
- NFR-6.2 *(revised)* The full application stack shall be deployable with standard Docker Compose definitions on a cloud VM or local development environment.

### 5.7 Data protection and privacy
- NFR-7.1 Uploaded resumes contain PII and shall not be used to train any third-party model beyond the scoped opt-in API calls.
- NFR-7.2 Users shall be able to request deletion of their uploaded resumes and derived data.
- NFR-7.3 *(revised)* Uploaded resumes shall be encrypted at rest in object storage (MinIO / S3) and access controlled via JWT authentication.

### 5.8 Reproducibility
- NFR-8.1 For the same input and the same `engine_fingerprint`, any two deployments of the core engine shall produce identical rounded scores, identical ranking order, and identical matched/missing lists.
- NFR-8.2 Cross-hardware floating-point drift (order of 1e-5) shall be absorbed by FR-3.5's rounding and tie-break rule and shall be covered by a CI test across at least two CPU architectures.


## 6. System architecture overview

The System is a hybrid: a Spring Boot backend handles authentication, orchestration, persistence; a Python core engine performs extraction, matching and scoring; Google Vertex AI (Gemini) is invoked for coaching explanations and non-engineering extractions.

```mermaid
flowchart TB
    subgraph CORE["Core Engine (FastAPI) — Deterministic Core"]
        direction LR
        X["extract"] --> S["segment"] --> D["dictionary skills"] --> N["NER (edu/exp)"] --> M["lookup-table match"] --> A["ATS rules"] --> T["template explain"]
    end
    W["Cloud web app
full history, 5 roles,
AI narrative, JD match"]
    CORE --> W
    W -.->|HTTPS (ADC)| LLM[["Google Vertex AI (Gemini)"]]
```

*Figure 1: Deterministic core engine serving the cloud web app on GCP.*

### 6.1 Layer responsibilities

| Layer | Responsibility |
|---|---|
| Client (HTML + CSS + vanilla JS) | Upload, dashboard, JD match, feedback. |
| Spring Boot Backend | JWT auth, RBAC, orchestration, persistence, EMA update job, snapshot export. |
| PostgreSQL + MinIO | Users, resume versions, profiles, roles, versioned skill vectors, recommendations, feedback; resume files. |
| Core engine (Python) | Text extraction, segmentation, dictionary + NER extraction, normalization, vector lookup matching, ATS scoring, template explanation, engine fingerprint. |
| LLM API | Coaching narrative and opt-in extraction only. |
| Training pipeline | Offline fine-tuning and distillation; produces hashed ONNX artifacts consumed by the core engine. |


## 7. Data requirements

| Entity | Key attributes | Notes |
|---|---|---|
| User | id, email, password_hash, role, created_at | `role ∈ {USER, ADMIN}` (FR-12.1). |
| Resume | id, user_id, file_ref, uploaded_at, version | One row per uploaded version (FR-1.5); `file_ref` is an object-storage key. |
| ParsedProfile | resume_id, name, email, phone, skills[], education, experience, ats_score, ats_max_score, ats_checks, explanation | Structured extraction and analysis output. |
| Role | id, title, description | Curated job role. |
| SkillVector | role_id, skill, weight, version_timestamp, current | Versioned EMA store (FR-7.1 to 7.4). |
| Recommendation | id, user_id, resume_id, role_id, match_score, matched_skills, missing_skills, created_at | One row per computed recommendation, tied to the resume version that produced it. |
| Feedback | id, recommendation_id, skill_vector_version_id, is_helpful, created_at | Feedback signal (FR-10.1 to 10.2). |
| Weights snapshot (file) | snapshot_id, created_at, sha256, weights{role→skill→weight} | Exported JSON, shipped inside the core engine (FR-7.5). Not a table. |
| Engine fingerprint (response field) | engine_version, ner_model_sha, embed_model_sha, taxonomy_sha, weights_snapshot_id | Returned with every analysis (FR-11.2). |

Physical schema: [Database Schema](database-schema.md) and the Flyway migration under `backend/src/main/resources/db/migration/`.


## 8. Other requirements

### 8.1 Licensing
Source code is proprietary, all rights reserved (repository LICENSE). Local, non-commercial use and evaluation are permitted; commercial use, redistribution and modification outside the contribution process require written permission. Open decision: the licence under which the Community Edition image is published (proprietary-but-free, source-available, or an OSI licence for the engine only). Third-party models and datasets carry their own licences (Apache-2.0 for the pretrained models in use; see [Datasets](datasets.md)).

### 8.2 Contribution model
Collaborator access is granted at the copyright holder's discretion. All changes go through pull requests to the protected default branch; see CONTRIBUTING.md.

### 8.3 Regulatory and compliance notes
The System is a student project and does not pursue formal certification. Section 5.7 and NFR-8.x reflect practice appropriate to this stage and should be revisited before any deployment where the System influences hiring decisions, at which point the EU AI Act's high-risk obligations (in force for employment systems from 2 August 2026) would apply to the deployer.


## Appendix A: Glossary

| Term | Meaning |
|---|---|
| Canonical skill taxonomy | A single, deduplicated vocabulary of skills that raw extracted text is mapped onto (§3.2). |
| Cosine similarity | A measure of the angle between two vectors, used to score how closely a candidate's skill profile matches a role's skill vector. |
| Decay parameter (α) | A value between 0 and 1 controlling how quickly the EMA update favours new data. |
| Deterministic core | The matching and scoring logic (§3.3, §3.9) that runs without LLM involvement and produces reproducible output. |
| Golden suite | A fixed set of resumes with expected outputs per engine version, used to prove parity (FR-11.6). |
| Distillation | Training a smaller "student" model to reproduce a larger "teacher" model's outputs (§3.13). |

## Appendix B: Feature priority matrix

### B.1 Product features

| Feature | Priority | Requirements | Status |
|---|---|---|---|
| Career Recommendation Engine | Urgent | FR-3.1 to 3.6 | Implemented; 3.6 planned (needs a real embedding run) |
| Editions and Result Parity | Urgent | FR-11.1 to 11.6 | Fingerprint mechanism + 2dp/tie-break rounding implemented; real model pinning, one shared release artifact, Docker image, and the golden-suite gate still planned |
| Temporal Skill-Vector Update | Urgent | FR-7.1 to 7.5 | Implemented |
| Resume Upload and Parsing | High | FR-1.1 to 1.7 | Implemented; DOCX planned |
| Skill Normalization | High | FR-2.1 to 2.3 | 2.1 implemented |
| Skill Gap Analysis | High | FR-4.1 to 4.3 | Implemented; 4.2 planned |
| Results Dashboard | High | FR-6.1 to 6.3 | Implemented; match-score trend view planned |
| Roles and AI engine | High | FR-12.1 to 12.10 | Roles (USER, ADMIN), one product for every account, AI-engine locks and re-analysis implemented; exports and live weights planned |
| Model Training and Release | High | FR-13.1 to 13.5 | Planned |
| Explanation Generation | Medium | FR-5.1 to 5.4 | Implemented |
| Job Description Matching | Medium | FR-8.1 to 8.2 | Planned |
| ATS Compatibility Score | Medium | FR-9.1 to 9.4 | Implemented; 9.2 planned |
| Feedback Collection | Medium | FR-10.1 to 10.2 | Implemented |
| ESCO taxonomy migration | Low | §3.13 | Post-MVP |
| Skill-gap → learning resources | Low | n/a | Post-MVP |
| Match visualization | Low | n/a | Post-MVP |
| Batch analysis | Low | n/a | Stretch |
| Local LLM (Qwen3-0.6B) explanation | Low | n/a | Phase 3 experiment |

### B.2 Project setup and infrastructure

| Item | Priority | Status |
|---|---|---|
| Repository, license, CONTRIBUTING | High | Done |
| Branch protection (PR-only) | High | Done |
| Database schema incl. versioned skill vectors (Flyway V1) | Urgent | Done |
| Backend ↔ ML service API contract (`/analyze-file`) | Urgent | Done |
| Initial job-roles/skills dataset | High | Done (small, curated) |
| Community Dockerfile and compose | Urgent | Not started |
| Golden parity suite in CI | Urgent | Not started |
| Training pipeline and datasets | High | Not started |
| Web deployment on a single VM | High | Not started |

## Appendix C: Revision history

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | 2026-08-28 | Amitosh Biswas | Initial SRS draft (Word document). |
| 2.15 | 2026-10-22 | Amitosh Biswas | Engine version 0.5.5: headings the parser doesn't read (Projects, Certifications, Hackathons, ...) end the section above them, Internships count as Experience; each degree is paired with the institution line next to it in the direction the resume uses, with the year from its own line; plural institution keywords; 15 skills added (JUnit, Mockito, Maven, Hibernate, Spring Security, JPA, ...). Scored on GCP: field macro F1 84 % -> 85 % (DataTurks) and 90 % -> 91 % (unseen LiveCareer). |
| 2.15 | 2026-11-06 | Amitosh Biswas | Every field is read by the local engine: all 23 domains are `engine: local`, so no upload needs Google credentials and the LLM only writes the narrative. Non-engineering skills come from the all-domain dictionary and the Skills section (the IT-trained NER model's skill spans are not used there). Parser: job titles are never names, sentence fragments and placeholder companies are dropped, PDF mojibake is repaired, degrees no longer swallow their college. Domain detection compares the headline and the education-free opening with every catalogue role (agreement with the LiveCareer categories 42 % to about 50 %). `scripts/evaluate_resume_categories.py` added. |
| 2.14 | 2026-10-22 | Amitosh Biswas | Engine version 0.5.4: an institution the NER model cut short (e.g. "Pune University" from "Savitribai Phule Pune University") is restored from the Education line it came from. Scored on GCP with the same harness: the served model keeps 84 % (DataTurks) and 90 % (unseen LiveCareer) field macro F1, institution unchanged. |
| 2.14 | 2026-11-06 | Amitosh Biswas | One version of the product: the Free/Premium tiers, the per-account AI allowance (FR-12.9), `PREVIEW_MODE`, the `PREMIUM_USER` role, the history and role-count limits, and the Premium UI (badges, upgrade prompts, pricing) are removed. Every account gets five roles, the AI narrative, JD match and unlimited history. The operator keeps an optional daily AI budget. Local parser: education built from the section's own lines, repaired experience, one-word names, Skills-section parsing. |
| 2.13 | 2026-10-22 | Amitosh Biswas | Engine version 0.5.3: the DOCX extractor also leaves out text a reader cannot see -- runs marked hidden, set under 3 pt, or white with no dark shading or highlight behind them (white text in a dark table cell stays) -- and counts it for the `no_hidden_text` ATS check, as the PDF extractor does (NFR-2.5). |
| 2.12 | 2026-10-22 | Amitosh Biswas | Job-market data now feeds the EMA skill weights (FR-7.6): open Bengaluru jobs are grouped by catalogue role daily, each skill's share of a role's jobs becomes its EMA signal, the weights are installed in the core engine automatically, and users see the most-asked skills for their top roles. |
| 2.11 | 2026-10-22 | Amitosh Biswas | Engine version 0.5.2, from a hidden-text prompt-injection test: NFR-2.5 added. The PDF extractor leaves out white, tiny and off-page text (white text on a dark filled shape stays) and a new 10-point ATS check, `no_hidden_text`, reports it, so the base maximum is 90. The LLM extraction prompt delimits the resume and treats it as data; extracted skills not found in the resume text are dropped; profile fields are length-capped. |
| 2.10 | 2026-10-21 | Amitosh Biswas | Frontend redesigned as a clean dashboard (commit 3c51f78, 2026-10-20), replacing the comic-book UI: sidebar with resume versions, resume analyzer, dashboard tabs (overview, role matches, JD match). Bootstrap is no longer used; the client is HTML, one hand-written stylesheet and vanilla JavaScript (§2.4, §6). Tested end to end against the real backend. FR-8.1 wording follows the new JD match tab. No API change. |
| 2.9 | 2026-10-21 | Amitosh Biswas | Engine version 0.5.1, from the first end-to-end test of the new frontend: the local parser reads Indian mobile numbers written as two groups of five ("+91 98765 43210"); the template explanation names what to fix in plain words instead of check identifiers and shows the top match as a percentage; JD match no longer counts job-ad boilerplate ("hiring", "design", "equity", "inclusion", "compensation") as required skills; 17 common tools added to the engineering skill taxonomy (Kafka, Redis, GraphQL, FastAPI, Django, MongoDB and others). |
| 2.8 | 2026-10-20 | Amitosh Biswas | Engine version 0.5.0: the local NER model is our fine-tune of `yashpwr/resume-ner-bert` (run 1 teacher, `ml-service/training/RESULTS.md`): field macro F1 84 % on DataTurks test (corrected key) and 90 % on 20 unseen LiveCareer resumes, against 76 % and 64 % for the upstream model. Loaded from a local directory, pinned by the SHA-256 of its weights. The distilled student (65M parameters, 81 % / 90 %) is kept as the smaller option. |
| 2.7 | 2026-10-10 | Amitosh Biswas | Engine version 0.4.1: the local parser reports each NER entity's text exactly as written in the resume (from the entity's character offsets), instead of the model's rebuilt tokens, which put spaces around punctuation ("Technical Lead / Operations Manager" for "Technical Lead/Operations Manager"). |
| 2.6 | 2026-10-08 | Amitosh Biswas | Training-data labelling uses `gemini-3.5-flash-lite` (prompt v3, minimal thinking): 97 % macro F1 on 20 hand-labelled LiveCareer resumes and 93 to 100 % recall on 20 independent DataTurks resumes, about $0.0035 per resume. Data preparation and labelling tooling added (`ml-service/training/data_prep/`). General skill taxonomy cleaned of posting boilerplate (1,185 to 1,155 skills). Runtime Gemini model unchanged (`gemini-2.5-flash-lite`). |
| 2.5 | 2026-10-04 | Amitosh Biswas | Local NER model set to `yashpwr/resume-ner-bert`, pinned to commit `3ea6ecf` (49 % token F1 on 220 annotated real resumes). Parser fixes: word-level entity aggregation, newline-preserving chunks, name from the resume's first lines, institution fallback, model revision actually applied at load time. Field macro F1 baseline: 60 % (DataTurks held-out) and 64 % (20 unseen LiveCareer resumes). Engine version 0.4.0. |
| 2.4 | 2026-09-29 | Amitosh Biswas | Frontend rewritten from Angular 22 to static HTML + Bootstrap 5.3 + vanilla JavaScript (ES modules, no build step, one page per screen), so it can be debugged with plain browser DevTools; tests move from Vitest to Node's built-in `node --test`. No API or behaviour change. FR-12.4 wording: "routes" → "pages". |
| 2.3 | 2026-09-14 | Amitosh Biswas | Ten more Premium domains (core engineering, science & research, consulting & project management, retail & e-commerce, social services, banking & insurance, quality/safety/EHS, real estate & property, veterinary/agriculture/environment, manufacturing & production), for 23 domains and 260 catalogue roles in total; non-IT engineers are no longer mis-routed. JD-targeted match (FR-14, Premium). Engine version 0.3.0. |
| 2.2 | 2026-09-14 | Amitosh Biswas | Tiers v2: recommendations gate on depth and volume, not on domain. Free accounts get a monthly allowance of AI analyses for non-engineering fields (FR-12.9); Premium is for every field (narrative, 5 roles, unlimited); Community Edition is engineering-only with no LLM (FR-12.10). LLM cost controls and per-call usage ledger added; `gemini-2.5-flash-lite` default. |
| 2.1 | 2026-09-14 | Amitosh Biswas | Career OS scope: all job domains, not only engineering. Added FR-12.6 to 12.8 (domain detection, engine/tier per domain, re-analysis, admin bootstrap). LLM provider changed to Gemini on Vertex AI with Application Default Credentials (no API keys); Groq optional. DOCX input added. Engine version 0.2.0; `taxonomy_sha` now covers both taxonomies, both role catalogues and `domains.json`. |
| 2.0 | 2026-09-10 | Amitosh Biswas | Converted to markdown in `docs/`. Added editions (Community/Web Free/Web Premium), result-parity requirements (§3.11), tier gating (§3.12), model training and release (§3.13), Community hardware spec (§4.2), reproducibility NFRs (§5.8), offline and latency NFRs. FR-1.2 changed from LLM extraction to local NER default. FR-3.2 now uses weights snapshot. FR-5.x: template explanation default, LLM narrative Premium. Environment updated to Angular 22, Spring Boot 3.3, MinIO, ONNX Runtime, Groq or Gemini. Statuses updated to reflect the implemented backend, frontend and EMA job. |
