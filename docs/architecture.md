# System architecture

> Project: Smart Resume Analyser and Job Recommendation System
> Scope: a candidate-facing resume analyser, delivered as a cloud platform on Google Cloud Platform (GCP) as one web app for every account. It runs one deterministic core engine with an explainable score, and calls Google Vertex AI for specific tasks. The offline self-hosted distribution is archived in [`docs/archive/community-edition.md`](archive/community-edition.md).

## 1. Why this architecture

Most "AI resume analyser" projects wrap a single chat-style LLM prompt around the whole problem. That makes results unreproducible (the same resume scores differently on two runs, even at temperature 0, as the [research](editions-and-parity.md#6-research-behind-the-design) shows), unexplainable, and dependent on whichever LLM endpoint was reached.

This system is built the opposite way. A deterministic core engine does all extraction, normalization, matching and scoring with plain code and pinned local models: regex, a lookup table, a local NER model, precomputed embedding vectors, cosine similarity and an integer ATS rubric. An LLM handles two narrow tasks: turning already-computed numbers into a coaching narrative, and extracting non-engineering resumes across the 22 other domains. The LLM never decides a score or a ranking, so results are reproducible across all tiers ([SRS §3.11](srs.md#311-core-engine-architecture-and-result-parity-revised-in-v22)).

## 2. Component diagram

Three deployable services, all implemented, hosted on GCP:

```mermaid
flowchart TB
    subgraph Client["Client — Browser (HTML + CSS + vanilla JS)"]
        UI["Web pages\n(Upload · Dashboard · Feedback · Tier badges)"]
    end

    subgraph Backend["Spring Boot Backend (backend/)"]
        API["REST controllers\n/auth /resumes /recommendations /feedback /roles/{id}/skill-vectors"]
        AUTH["auth + account\nSpring Security, JWT, UserRole"]
        ORCH["resume.ResumeService\n(one /analyze-file call per upload)"]
        SV["skillvector\nEMA update, snapshot export"]
        REPO["Spring Data JPA + Flyway"]
        STORE["ResumeStorageService\n(MinIO / Cloud Storage)"]
        CLIENT["client.MlServiceClient"]
    end

    subgraph ML["Core engine / ML Service (ml-service/)"]
        ROUTER["FastAPI routers\n/parse /parse-file /match /ats-score /analyze /analyze-file /health"]
        UPLOAD["document_extraction/\nPDF → text (column-aware)"]
        SECT["sectioner.py\nheadings → sections"]
        DICT["dictionary_skills.py\nAho-Corasick over taxonomy"]
        PARSER["parser.py\n→ local NER (default) | LLM (non-eng)"]
        NER["local_ner_parser.py\nresume-ner-bert"]
        NORM["normalizer.py"]
        MATCH["matcher.py\nvector lookup, weighted mean,\n2-dp rounding"]
        VEC["skill_vectors.npy / role_vectors.npy\nweights_snapshot.json"]
        EMB["embeddings.py\n(fallback for unknown skills)"]
        ATS["ats_score.py"]
        GAP["gap_analysis.py"]
        EXPL["explainer.py\ntemplate (default) | llm narrative"]
        FP["engine_fingerprint"]
    end

    subgraph Training["GCP Cloud Training Track (ml-service/training/)"]
        LABEL["Training-data labelling\n(Gemini 3.5 Flash-Lite, offline)"]
        TRAIN_NER["NER Continue-Training & Distillation"]
        TRAIN_EMB["SentenceTransformer Fine-Tuning"]
        LABEL --> TRAIN_NER
    end

    DB[("PostgreSQL 15\nusers · resumes · parsed_profiles · roles\nskill_vectors · recommendations · feedback")]
    MINIO[("MinIO / Cloud Storage\nresume files")]
    LLM[["Google Vertex AI (Gemini 2.5 Flash Lite)\nCoaching narrative (ADC)"]]

    UI -->|HTTPS / REST / JSON + JWT| API
    API --> AUTH
    API --> ORCH
    API --> SV
    ORCH --> STORE --> MINIO
    ORCH --> REPO --> DB
    SV --> REPO
    ORCH --> CLIENT -->|HTTP multipart, internal| ROUTER

    ROUTER --> UPLOAD --> SECT
    SECT --> DICT --> NORM
    SECT --> PARSER --> NER
    PARSER -.->|PARSER_BACKEND=llm| LLM
    ROUTER --> MATCH --> NORM
    MATCH --> VEC
    MATCH -.-> EMB
    ROUTER --> ATS
    ROUTER --> GAP
    ROUTER --> EXPL
    EXPL -.->|explainer=llm| LLM
    ROUTER --> FP
    SV -.->|weights_snapshot.json per release| VEC
    Training -.->|Trained models & vectors| ML

    style ML fill:#eef6ff,stroke:#4a7dbd
```

## 3. The deterministic-core / narrow-LLM split

No path that produces a number touches the LLM:

```mermaid
flowchart LR
    subgraph Deterministic["Deterministic core — reproducible, explainable, no LLM, no network"]
        direction TB
        S["sectioner* + dictionary_skills*"]
        NER["local NER (pinned model)"]
        N["normalizer.py\nraw skill → canonical"]
        M["matcher.py\nvector lookup · cosine · round(2) · tie-break"]
        A["ats_score.py\nregex + keyword rubric"]
        G["gap_analysis.py\nset difference"]
        T["explainer.py (template*)"]
        S --> N --> M --> G
        NER --> N
        M --> T
        A --> T
        G --> T
    end
    subgraph LLMScoped["LLM-scoped — optional, behind LLMClient Protocol"]
        direction TB
        P["parser.py LLM path\n(opt-in extraction)"]
        E["explainer.py (llm)\nNarrative only"]
    end
    P -.->|profile.skills| N
    M -.->|matches| E
```

Properties that follow:

- Reproducibility. The same resume text and the same `engine_fingerprint` give the same profile, ATS score, matches and gaps. Cross-CPU floating-point drift (≈ 1e-5) is absorbed by rounding to two decimals before ranking, with a deterministic tie-break ([SRS FR-3.5](srs.md#33-career-recommendation-engine)); the matcher's vectors are shipped constants, so it has no drift at all.
- Graceful degradation (NFR-3.1). An LLM outage cannot affect a score. The template explainer is the fallback, so an outage degrades only the coaching narrative field.
- Deterministic score path (NFR-3.2). Nothing on the score path downloads or calls out to third-party generative models.

## 4. The cloud web app

```mermaid
flowchart TB
    CORE["Core engine artifact\nlocal NER · taxonomy · vector tables · weights snapshot vN · ATS rules"]
    W["Cloud web app
accounts · dashboard · feedback
full history · 5 roles
LLM narrative (Gemini via ADC)
all domains · JD match"]
    CORE --> W
```

Every account uses the same deterministic core engine; the narrative coaching is an added field on top of the same base score. The historical offline self-hosted design is archived in [`docs/archive/community-edition.md`](archive/community-edition.md).

## 5. Deployment view (Google Cloud Platform)

```mermaid
flowchart LR
    subgraph Browser["Browser Client"]
        SPA["Web client (HTML/JS)"]
    end
    subgraph GCP["Google Cloud Platform (GCP)"]
        subgraph VM["GCP Compute Engine (Option A) — Docker Compose"]
            FE["frontend (static, nginx) :4200"]
            BE["backend :8080"]
            MLC["ml-service :8000\n(FastAPI deterministic engine)"]
            PG[("PostgreSQL :5432")]
            MN[("MinIO / Storage :9010")]
        end
        subgraph Training["GCP Training Instance"]
            GPU["GPU Instance (NVIDIA T4)\nTraining & Distillation"]
        end
        VERTEX[["Google Vertex AI\n(Gemini 2.5 Flash Lite via ADC)"]]
    end

    SPA -- HTTPS --> FE
    SPA -- HTTPS --> BE
    BE -- internal HTTP --> MLC
    BE -- JDBC --> PG
    BE -- S3 API --> MN
    MLC -. HTTPS (ADC) .-> VERTEX
    GPU -. Trained ONNX Models .-> MLC
```

The application is deployed to Google Cloud Platform with Docker Compose on an `e2-standard-4` Compute Engine instance (Option A). It is quick to set up and simple to run, and the user's $300 GCP credit pays for it. Model training and distillation jobs run on an on-demand GCP GPU VM (e.g. T4) because the local machine can't handle them.

## 6. Data flow summary

Request lifecycle for `POST /analyze-file` (the backend's one call per upload). Full breakdown in [DFD](dfd.md).

1. Extract: `document_extraction/pdf_extractor.py` produces column-aware text.
2. Segment*: `sectioner.py` splits the text into Skills / Experience / Education / other by heading detection (fallback: whole text).
3. Contact: email/phone regex.
4. Skills: `dictionary_skills.py`* matches taxonomy variants over the whole text; NER "Skills" spans are merged in for recall.
5. NER: `local_ner_parser.py` runs the pinned model on the Experience and Education sections only (today: whole text in 380-word chunks).
6. Normalize: `normalizer.py` maps every skill to its canonical form.
7. Match: `matcher.py` looks up precomputed vectors* (MiniLM only for out-of-taxonomy skills), applies the weights snapshot*, ranks by cosine similarity rounded to 2 dp* with a deterministic tie-break*.
8. ATS: `ats_score.py` runs independently on the raw text.
9. Gaps: `gap_analysis.py` projects `missing_skills`.
10. Explain: `explainer.py` calls the LLM for the narrative, or renders the template when the AI engine is unavailable. Either way it cannot change a number.
11. Fingerprint*: the response carries `engine_fingerprint`.
12. Persist (web editions): the backend stores `Resume`, `ParsedProfile` (incl. ATS and explanation), `Recommendation` rows; feedback later drives the EMA update and the next weights snapshot.

## Related documents

- [Editions & Parity](editions-and-parity.md): parity mechanism, pipeline restaging, PC spec, costs, research
- [High-Level Design](hld.md) · [Low-Level Design](lld.md) · [DFD](dfd.md) · [Process Flow](process-flow.md)
- [Abstraction Overview](abstraction-overview.md) · [Tech Stack](tech-stack.md) · [SRS v2.0](srs.md)
