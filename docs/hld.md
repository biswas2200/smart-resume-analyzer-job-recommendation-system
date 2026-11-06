# High-level design (HLD)

Companion to [System Architecture](architecture.md), which explains why the system has this shape. This page specifies each layer's responsibility, its interfaces, and the design decisions fixed at this level, based on [SRS v2.0 §6](srs.md#6-system-architecture-overview).

## 1. Layers and responsibilities

| Layer | Responsibility | Status |
|---|---|---|
| Client (static multi-page web client: HTML + one hand-written stylesheet + vanilla JS) | Resume analyzer (upload, versions, parsed profile), dashboard (ATS checks with fixes, role matches with gaps, JD match), feedback controls. No business logic. | Implemented |
| Spring Boot backend | JWT auth, RBAC (`USER` / `ADMIN`), orchestration (one ML call per upload), persistence, MinIO storage, EMA skill-vector job, weights snapshot export. | Implemented; snapshot planned |
| PostgreSQL + MinIO | Users, resume versions, parsed profiles (incl. ATS + explanation), roles, versioned skill vectors, recommendations, feedback; resume files. | Implemented (Flyway `V1`) |
| Core engine / ML service | PDF extraction, section segmentation, dictionary + NER extraction, normalization, vector-table matching, ATS scoring, gap analysis, template explanation, engine fingerprint. Optional LLM narrative / extraction. | Implemented (current pipeline); restaging planned |
| Google Vertex AI (Gemini) | Coaching narrative only (every field is read locally); an opt-in extraction path exists. Never scores or ranks. | Implemented |
| Training pipeline | Cloud fine-tuning and distillation on GCP GPU instance; hashed ONNX release artifacts. | Planned (step 7) |
| Community Edition packaging | Standalone offline Docker image and CLI. | Archived; see [`docs/archive/community-edition.md`](archive/community-edition.md) |

## 2. Component responsibilities (ML service)

Modules in `ml-service/app/`; `*` marks planned ones.

| Module | Responsibility | LLM? |
|---|---|---|
| `routers/analyze.py` | `POST /parse`, `/match`, `/ats-score`, `/analyze`. Thin; delegates to services. | No |
| `routers/upload.py` | `POST /parse-file`, `/analyze-file`. Dispatches to a `DocumentTextExtractor` by extension. | No |
| `services/document_extraction/` | `DocumentTextExtractor` Protocol + `PdfTextExtractor` (pdfplumber, column-aware) + registry. | No |
| `services/sectioner.py`* | Heading-based segmentation into Skills / Experience / Education / other; whole-text fallback. | No |
| `services/dictionary_skills.py`* | Aho-Corasick match of taxonomy variants over the text; deterministic, linear time. | No |
| `services/parser.py` | Text → `ResumeProfile`; routes to local NER (default) or LLM (`PARSER_BACKEND=llm`). | Opt-in |
| `services/local_ner_parser.py` | Runs the pinned NER model on the Experience/Education sections*, chunked under the 512-token limit; clusters flat entities into records; regex email/phone/dates. | No |
| `services/normalizer.py` | Raw skill → canonical taxonomy entry. | No |
| `services/embeddings.py` | sentence-transformers wrapper; at runtime only for out-of-taxonomy skills once vectors are precomputed*. | No |
| `services/matcher.py` | Candidate vector vs. each role vector (precomputed table*, weights snapshot*), cosine similarity, round to 2 dp before sort*, tie-break by role name*; matched/missing as exact set ops. | No |
| `services/ats_score.py` | Rule-based ATS rubric; every point traceable to a named check. | No |
| `services/gap_analysis.py` | Projects `missing_skills` per matched role. | No |
| `services/explainer.py` | `TemplateExplainer`* (default) renders matched/missing + ATS breakdown; `LLMExplainer` for `explainer=llm`. Neither can change a number. | Only `llm` |
| `services/llm_client.py` | `LLMClient` Protocol + `GroqLLMClient` / `GeminiLLMClient`. | n/a |
| `config.py` | Settings; `ENGINE_VERSION`* and `engine_fingerprint`* (engine version + hashes of NER model, vector table, taxonomy, weights snapshot). | n/a |
| `scripts/precompute_vectors.py`* | Build-time embedding of every canonical skill and role → `data/*.npy` + sha256. | No |
| `training/`* | `train_ner.py`, `train_embed.py`, dataset converters, `DATASETS.md`; separate requirements. | No |

## 3. Design decisions

### 3.1 Deterministic core, narrow LLM footprint
Every score or ranking is computed by plain code and pinned local models. The LLM's only jobs are the narrative and an opt-in extraction path (SRS §2.5, FR-5.3).

### 3.2 LLM access behind a Protocol
`LLMClient.complete(system_prompt, user_prompt) -> str`; the full test suite runs with a `FakeLLMClient`, no network.

### 3.2b Parsing backend behind the same kind of seam
`parser.parse_resume()` routes to `local_ner_parser` or the LLM path by config; the NER module separates the impure pipeline from the pure entity-clustering logic so heuristics are unit-testable without the model.

### 3.2c File format behind an adapter interface
`DocumentTextExtractor` + registry; DOCX is one new class away.

### 3.2d Explanation backend behind the same seam
`Explainer` Protocol with `TemplateExplainer` (default) and `LLMExplainer`; the narrative uses the LLM explainer and falls back to the template when the AI engine is unavailable, so a missing API key never blocks a result and prose never touches the score.

### 3.3 Two-stage skill matching: normalize, then embed
Skills are canonicalized before anything numeric happens; matched/missing lists are exact set operations, not fuzzy distances.

### 3.4 Role vectors as the (weighted) mean of per-skill embeddings
Candidate and role are each the mean of their skills' vectors; ranking by cosine similarity. With the weights snapshot the mean becomes weighted (FR-3.2).

### 3.5 Backend as orchestrator, not a second scoring engine
The backend calls `/analyze-file` once per upload and persists the result; deterministic logic lives in exactly one place (NFR-5.1).

### 3.6 Temporal skill-vector store (implemented)
`SkillVectorService` applies `new = α·signal + (1−α)·old` (α = `app.skill-vector.alpha`, default 0.3) once a role passes `app.skill-vector.feedback-threshold` helpful/not-helpful votes. Every update inserts a new versioned row (`current` flag) and keeps the prior versions.

### 3.7 Graceful LLM degradation
An LLM outage cannot affect a score; the template fallback means it never blocks a result.

### 3.8 One core engine, three editions
Every edition runs a single versioned artifact (code + hashed models + taxonomy + vector tables + weights snapshot). Every response carries `engine_fingerprint`; a golden suite executed inside the Community image and against the web API must match before a release ships (FR-11.x). Premium only adds fields.

### 3.9 Precompute the finite side of the match
Because the matcher only sees canonical skills, all skill and role vectors are computed at build time and shipped as constants. The embedding model leaves the hot path and cross-CPU drift leaves the matcher. Rounding to 2 dp before sorting, plus a deterministic tie-break, covers the remaining numeric paths (FR-3.5, FR-3.6).

### 3.10 Roles at the module boundary
`SecurityConfig` decides only whether a request is authenticated; which role an endpoint needs is declared on that endpoint with `@PreAuthorize` (already the pattern for `POST /roles/{id}/skill-vectors/recompute`). There are two roles, `USER` and `ADMIN`; every account gets the same product (FR-12.x).

### 3.11 Model releases are gated and shared
Training happens offline; a new model ships only if held-out quality is not below the previous release and the golden suite is regenerated and reviewed. All editions receive the same model at the same precision (FR-13.x).

## 4. Interfaces between layers

| From → To | Protocol | Payload | Auth |
|---|---|---|---|
| Client → Backend | HTTPS / REST | JSON | JWT bearer |
| Backend → ML Service | HTTP multipart (internal), `POST /analyze-file?top_n=N&explainer=template|llm`* | JSON | none (internal network) |
| Community CLI → ML Service | in-process / `localhost:8000` | JSON, HTML report | none |
| Backend → PostgreSQL | JDBC (Flyway-managed schema) | SQL | env credentials |
| Backend → MinIO | S3 API | object bytes | env credentials |
| ML Service → LLM API | HTTPS / REST (only when `explainer=llm` or `PARSER_BACKEND=llm`) | JSON | API key (env) |
| Training → ML Service | files: hashed ONNX models, `vectors.sha256`, `weights_snapshot.json` | n/a | n/a |

## 5. Non-functional design targets

Carried from [SRS §5](srs.md#5-non-functional-requirements):

- Performance: parsing ≤ 15 s (NFR-1.1); matching over ≤ 100 roles ≤ 2 s (NFR-1.2); Community ≤ 3 s and ≤ 1.5 GB RSS per two-page resume on 2 cores / 4 GB (NFR-1.3), measured by `scripts/bench.py`.
- Security: JWT ≤ 24 h; bcrypt; TLS; secrets in env only (NFR-2.x).
- Reliability: an LLM outage never fails a request (NFR-3.1); the engine runs with zero network (NFR-3.2).
- Scalability: stateless backend (NFR-4.1).
- Maintainability: deterministic and LLM modules are separable (NFR-5.1); the runtime image carries no training dependencies (NFR-5.2).
- Usability: ≤ 3 actions to a recommendation (NFR-6.1); Community runs with one `docker run` (NFR-6.2).
- Privacy: PII is never used to train third-party models (NFR-7.1); deletion on request (NFR-7.2); Community sends no telemetry (NFR-7.3).
- Reproducibility: identical output across editions and CPU architectures for the same fingerprint (NFR-8.1 and 8.2).

## Related documents

- [System Architecture](architecture.md) · [Editions & Parity](editions-and-parity.md) · [Low-Level Design](lld.md)
- [Abstraction Overview](abstraction-overview.md) · [Tech Stack](tech-stack.md) · [SRS v2.0](srs.md)
