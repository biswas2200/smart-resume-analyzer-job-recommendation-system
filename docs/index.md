# Smart Resume Analyser and Job Recommendation System: documentation

An AI-assisted resume analyser and career recommendation system. Its core engine is deterministic: local NER extraction, taxonomy normalization, embedding-based skill-to-role matching and rule-based ATS scoring. An LLM is used in two optional places, a coaching narrative and an opt-in extraction path. It never rewrites resumes and never produces a score.

The product is a hosted cloud platform on Google Cloud Platform (GCP) as one product for every account. It runs one deterministic core engine and calls Google Vertex AI (Gemini) for the 22 non-engineering domains and for coaching narratives. The original offline, self-hosted distribution is archived in [`docs/archive/community-edition.md`](archive/community-edition.md). [Result Determinism & Parity](editions-and-parity.md) covers the deterministic engine design, and [SRS v2.0](srs.md) the requirements.

These docs live under `docs/` and are built with MkDocs (see the last section).

## Where to start

If you're new to the project, read in this order:

1. [SRS](srs.md)
2. [Abstraction Overview](abstraction-overview.md)
3. [System Architecture](architecture.md)
4. [Result Determinism & Parity](editions-and-parity.md)
5. [HLD](hld.md)
6. [Use Case Diagram](use-case-diagram.md)
7. [DFD](dfd.md) and [Process Flow](process-flow.md)
8. [Entity Diagram](entity-diagram.md) and [Database Schema](database-schema.md)
9. [Class Diagram](class-diagram.md) and [Entities & Fields](entities-and-fields.md)
10. [LLD](lld.md)
11. [Datasets](datasets.md)

[UML Diagrams §2](uml-diagrams.md#2-reading-order-for-reviewers-new-to-the-project) explains why this order.

## Document index

| Document | Covers |
|---|---|
| [SRS v2.0](srs.md) | Functional and non-functional requirements, including the cloud web app, result determinism, model training |
| [Abstraction Overview](abstraction-overview.md) | The market gap; the deterministic-core / LLM abstraction; skills as a versioned vector space; the hosted product |
| [System Architecture](architecture.md) | Component diagram, deterministic-vs-LLM split, GCP deployment view |
| [Result Determinism & Parity](editions-and-parity.md) | Core engine determinism; restaged pipeline; cloud costs; fine-tuning; research |
| [High-Level Design (HLD)](hld.md) | Layer responsibilities, main design decisions, non-functional targets |
| [Low-Level Design (LLD)](lld.md) | Module design grounded in the real code, API contracts, sequence diagram, backend modules |
| [Use Case Diagram](use-case-diagram.md) | Actors, use cases, implemented vs. planned |
| [Data Flow Diagram (DFD)](dfd.md) | Level 0 context diagram, Level 1 process breakdown |
| [Process Flow](process-flow.md) | Activity diagrams: analyze, upload → dashboard, feedback → EMA, model release |
| [UML Diagrams](uml-diagrams.md) | Index of all UML views, plus the component diagram |
| [Entity Diagram](entity-diagram.md) | Conceptual entity-relationship diagram |
| [Database Schema](database-schema.md) | ERD, the Flyway schema, the versioned EMA skill-vector table, snapshot export |
| [Class Diagram](class-diagram.md) | ML-service classes and backend JPA entities |
| [Entities & Fields](entities-and-fields.md) | Source for every entity/model, field by field |
| [Tech Stack](tech-stack.md) | Per-layer breakdown, built vs. planned |
| [Datasets](datasets.md) | Open datasets for development, golden tests and training, with licence notes |
| [Archived: Community Edition](archive/community-edition.md) | Archived specifications, hardware profiles, and CLI design for the offline Docker edition |

## Project status

| Component | Status |
|---|---|
| ML service (`ml-service/`): extraction (local NER and dictionaries for every field), domain detection, normalization, matching (per-domain catalogues), ATS scoring, gap analysis, explanation, DOCX + PDF | Implemented, tested (`pytest tests/`) |
| Backend (`backend/`, Spring Boot): JWT auth, RBAC roles, admin upgrade path, resume upload + MinIO storage, re-analysis, recommendations with domain/lock state, feedback, EMA skill-vector update | Implemented |
| Frontend (`frontend/`, HTML + hand-written CSS + vanilla JS, dashboard layout with a sidebar): resume analyzer with versions, dashboard (ATS checks with fixes, domain badge, locked card), role matches, feedback, Premium JD match, tier badge | Implemented |
| Career OS domain split: engineering on the local engine; the other domains on Gemini (ADC); `engine` per domain in `domains.json` | Implemented (MVP, 2026-09-14) |
| Core-engine parity work: template explainer, pinned ONNX models, engine fingerprint, 2-dp rounding | Planned (step 1) |
| Restaged pipeline: sectioner, dictionary skills, precomputed vector tables | Planned (step 2) |
| Weights snapshot export / consumption | Planned (step 3) |
| Community Edition Docker image + CLI | Archived, paused in favor of GCP cloud hosting ([details](archive/community-edition.md)) |
| One version of the product (no tiers): five roles, AI narrative, JD match and full history for every account | Implemented (v2.14) |
| Golden parity suite in CI | Planned (step 6) |
| Training pipeline (`ml-service/training/`) | Planned (step 7): cloud training on GCP (Compute Engine / Vertex AI) |

## Building this documentation as a site

This folder is the content of a [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/) site configured by `mkdocs.yml` at the repository root:

```bash
pip install mkdocs-material
mkdocs serve          # local preview, run from the repo root
mkdocs build --strict # CI check: broken links fail the build
```
