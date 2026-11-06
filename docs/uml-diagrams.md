# UML diagrams: index

The UML documentation is split into one file per diagram type so each diagram stays readable. This page indexes them and also holds the one diagram with no other home, the component diagram.

| Diagram type | Where | What it shows |
|---|---|---|
| Use case diagram | [use-case-diagram.md](use-case-diagram.md) | Actors, use cases, implemented vs. planned |
| Class diagram | [class-diagram.md](class-diagram.md) | Pydantic models + services, backend JPA entities |
| Entity-relationship diagram | [entity-diagram.md](entity-diagram.md) | Conceptual/logical data model |
| Sequence diagram | [lld.md §3](lld.md#3-sequence-diagram-post-analyze-file-target-after-steps-13) | Call sequence for `POST /analyze` |
| Activity diagrams | [process-flow.md](process-flow.md) | User-journey flows with decision points |
| Component diagram | This page, §1 | Deployable/importable units and their dependencies |
| Deployment diagram | [architecture.md §5](architecture.md#5-deployment-view) | Container deployment per edition |
| Editions diagram | [editions-and-parity.md §1](editions-and-parity.md#1-the-promise-and-how-it-is-kept) | One core engine, three editions |

## 1. Component diagram

Import-time dependencies between components. This sits one level below the architecture diagram's boxes and network calls, and one level above the class diagram. Dashed borders mark planned components.

```mermaid
flowchart TB
    subgraph FE["Frontend component (HTML + vanilla JS)"]
        UIComp["Pages: upload · dashboard · feedback"]
        GuardComp["Lock and JD rules\n(dashboard-rules.js)"]
    end

    subgraph BE["Backend component (Spring Boot)"]
        AuthComp["auth\n(Spring Security + JWT)"]
        AccountComp["account\n(User, UserRole)"]
        ResumeComp["resume\n(upload, versions, MinIO)"]
        RecComp["recommendation"]
        FeedbackComp["feedback"]
        SkillVecComp["skillvector\n(EMA job, snapshot export*)"]
        ClientComp["client\n(MlServiceClient, REST)"]
    end

    subgraph MLSvc["Core engine / ML service component (FastAPI)"]
        RouterComp["routers\n(analyze + upload)"]
        SchemaComp["schemas\n(+ engine_fingerprint*)"]
        ExtractComp["document_extraction\n(PdfTextExtractor)"]
        SectionComp["sectioner*"]
        DictComp["dictionary_skills*"]
        ParserComp["parser"]
        NerComp["local_ner_parser"]
        NormComp["normalizer"]
        MatchComp["matcher"]
        VecComp["vector tables*\n(skill_vectors.npy, role_vectors.npy)"]
        EmbedComp["embeddings\n(fallback for unknown skills)"]
        AtsComp["ats_score"]
        GapComp["gap_analysis"]
        ExplainComp["explainer\n(template* | llm)"]
        LLMClientComp["llm_client"]
        ConfigComp["config\n(+ ENGINE_VERSION*)"]
    end

    subgraph CLI["Community CLI component* (Docker)"]
        CliComp["analyze <pdf> [--json|--html]"]
    end

    subgraph TRAIN["Training component* (offline)"]
        TrainComp["train_ner.py · train_embed.py\n→ hashed ONNX artifacts"]
    end

    DBComp[("PostgreSQL + MinIO")]
    GroqComp[["LLM API — Groq/Gemini\n(opt-in)"]]

    UIComp --> AuthComp
    UIComp --> ResumeComp
    UIComp --> RecComp
    UIComp --> FeedbackComp
    ResumeComp --> ClientComp
    ResumeComp --> RecComp
    FeedbackComp --> SkillVecComp
    AuthComp --> AccountComp
    ResumeComp --> DBComp
    RecComp --> DBComp
    SkillVecComp --> DBComp
    ClientComp -->|REST /analyze-file| RouterComp
    CliComp --> RouterComp

    RouterComp --> SchemaComp
    RouterComp --> ExtractComp
    RouterComp --> ParserComp
    RouterComp --> MatchComp
    RouterComp --> AtsComp
    RouterComp --> GapComp
    RouterComp --> ExplainComp
    ExtractComp --> SectionComp
    SectionComp --> DictComp
    SectionComp --> ParserComp
    ParserComp --> NerComp
    ParserComp -.->|opt-in| LLMClientComp
    DictComp --> NormComp
    MatchComp --> NormComp
    MatchComp --> VecComp
    MatchComp -.-> EmbedComp
    ExplainComp -.->|llm backend only| LLMClientComp
    LLMClientComp --> ConfigComp
    NerComp --> ConfigComp
    EmbedComp --> ConfigComp
    LLMClientComp -.->|HTTPS| GroqComp
    TrainComp -.->|release artifacts| NerComp
    TrainComp -.->|release artifacts| VecComp
    SkillVecComp -.->|weights_snapshot.json| VecComp

    style MLSvc fill:#eef6ff,stroke:#4a7dbd
    style CLI stroke-dasharray: 4 3
    style TRAIN stroke-dasharray: 4 3
```

`*` marks a planned component. [Editions & Parity §7](editions-and-parity.md#7-implementation-order) lists the step that adds each one.

## 2. Reading order for reviewers new to the project

1. [SRS v2.0](srs.md): what the system must do, per edition
2. [Abstraction Overview](abstraction-overview.md): why it is built this way
3. [System Architecture](architecture.md) and [Editions & Parity](editions-and-parity.md): the overall shape
4. [HLD](hld.md): layer responsibilities
5. [Use Case Diagram](use-case-diagram.md): user-facing scope
6. [DFD](dfd.md) and [Process Flow](process-flow.md): behaviour
7. [Entity Diagram](entity-diagram.md) and [Database Schema](database-schema.md): data model
8. [Class Diagram](class-diagram.md) and [Entities & Fields](entities-and-fields.md): implementation-level structure
9. [LLD](lld.md): API contracts and module detail, grounded in the real code
10. [Datasets](datasets.md): what to test and train on

## Related documents

- [Tech Stack](tech-stack.md)
- [Index](index.md)
