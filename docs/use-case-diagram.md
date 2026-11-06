# Use case diagram

Actors and use cases per [SRS v2.0](srs.md) §2.3 (user classes) and §3 (functional requirements). Each use case is tagged [Implemented] when it exists as working code today, or [Planned] with the implementation step from [Editions & Parity §7](editions-and-parity.md#7-implementation-order).

## Actors

| Actor | Description |
|---|---|
| Candidate (primary) | Job-seeking fresher or early-career professional. Uses the hosted app on GCP with an account; every resume version is kept, with the LLM coaching narrative and job-description matching. |
| Self-hosting user, Community Edition (archived) | Archived. This user was going to run the Docker image on their own machine ([details](archive/community-edition.md)). |
| System Administrator | Maintains taxonomy and role dataset, recomputes and exports skill-weight snapshots, manages cloud training, monitors health. |
| Institution / Placement Cell (future) | Batch analysis of many candidates against one role (stretch). |
| Google Vertex AI (Gemini 2.5 Flash Lite) (cloud service) | Invoked for the coaching narrative (UC6b) only; every field is read locally (UC2). Never initiates action; never affects a score. |

## Diagram

```mermaid
flowchart LR
    Free((Candidate))
    Admin((System<br/>Administrator))
    Institution((Institution /<br/>Placement Cell))
    LLM([Google Vertex AI — Gemini])

    subgraph SYS["Smart Resume Analyser and Job Recommendation System"]
        UC1["Upload resume (PDF)\n[Implemented — POST /resumes, /parse-file]"]
        UC2["Parse resume into\nstructured profile\n[Implemented — local NER; LLM non-eng]"]
        UC3["Normalize extracted skills\n[Implemented — normalizer.py]"]
        UC4["View ranked role\nrecommendations\n[Implemented — matcher.py]"]
        UC5["View skill-gap breakdown\n[Implemented — gap_analysis.py]"]
        UC6a["View template explanation\n[Planned — step 1]"]
        UC6b["View LLM coaching narrative\n[Implemented]"]
        UC7["Paste job description\nand get targeted match\n[Implemented]"]
        UC8["View ATS\ncompatibility score\n[Implemented — ats_score.py]"]
        UC9["Give helpful / not-helpful\nfeedback\n[Implemented — POST /feedback]"]
        UC10["View resume version\nhistory & score trend\n[Implemented; Free limited to 3 — step 5]"]
        UC11["View consolidated\ndashboard\n[Implemented — GET /recommendations/dashboard]"]
        UC12["Run full pipeline in\none call\n[Implemented — POST /analyze, /analyze-file]"]
        UC13["Maintain skill taxonomy\n[Planned — admin tool]"]
        UC14["Curate job-role dataset\n[Planned — admin tool]"]
        UC15["Monitor system health\n[Implemented — GET /health]"]
        UC16["Run batch analysis\n(N resumes vs. 1 role)\n[Stretch]"]
        UC17["Run engine offline via Docker\n[Archived — see archive/]"]
        UC18["Verify engine fingerprint\n[Planned — step 1]"]
        UC20["Export report
[Planned]"]
        UC21["Recompute skill vectors (EMA)\n[Implemented — POST /skill-vectors/recompute, ADMIN]"]
        UC22["Export weights snapshot\n[Planned — step 3, ADMIN]"]
        UC23["Train and release a model\n[Planned — step 7, ADMIN]"]
        UC24["Detect job domain\n[Implemented — domain_classifier.py]"]
        UC25["Re-analyse a resume at the\n\n[Implemented — POST /resumes/{id}/reanalyze]"]
        UC26["Promote an account\n[Implemented — PATCH /admin/users/{id}/role, ADMIN]"]
    end

    Free --> UC1
    Free --> UC4
    Free --> UC5
    Free --> UC6a
    Free --> UC8
    Free --> UC9
    Free --> UC10
    Free --> UC11
    Free --> UC18
    Free --> UC24
    Free --> UC25
    Admin --> UC26

    Free --> UC6b
    Free --> UC7
    Free --> UC20

    UC1 -.include.-> UC2
    UC2 -.include.-> UC3
    UC12 -.include.-> UC2
    UC12 -.include.-> UC8
    UC12 -.include.-> UC4
    UC12 -.include.-> UC5
    UC12 -.include.-> UC6a
    UC12 -.include.-> UC24
    UC11 -.include.-> UC12

    UC2 -.->|opt-in only| LLM
    UC6b --> LLM

    Admin --> UC13
    Admin --> UC14
    Admin --> UC15
    Admin --> UC21
    Admin --> UC22
    Admin --> UC23

    Institution --> UC16
```

## Use case detail (primary flows)

### UC4/UC5/UC6a/UC8/UC12: "Analyze my resume" (core flow)
- Actor: any candidate.
- Precondition: a PDF resume uploaded through the web interface.
- Main flow: text extraction → section segmentation → dictionary + NER extraction → normalization → vector-table matching → ATS rules → template explanation → response with `engine_fingerprint`.
- Postcondition: results are shown, and the web platform stores the `Resume`, `ParsedProfile` and `Recommendation` rows.
- Requirements: FR-1.x, FR-3.x, FR-4.x, FR-5.4, FR-9.x, FR-11.2.

### UC6b: "Get an LLM coaching narrative"
- Actor: any candidate.
- Main flow: after the core flow, the backend calls the ML service with `explainer=llm`; Google Vertex AI (Gemini) turns the already-computed numbers into prose. The base score is unchanged; the narrative is labelled non-deterministic.
- Requirements: FR-5.1 to 5.4, FR-12.2.

### UC17/UC18: "Core Engine Result Parity & Fingerprint Verification"
- Actor: candidate / auditor / administrator.
- Main flow: the returned `engine_fingerprint` can be checked against `GET /health` on the deployment. A matching fingerprint verifies that the models, vectors and weights are the same (FR-11.3). The standalone offline CLI is archived in [Archived: Community Edition](archive/community-edition.md).
- Requirements: FR-11.1 to 11.6, NFR-3.2, NFR-8.x.

### UC9 → UC21 → UC22: "Feedback improves the next release"
- Actors: candidate, then administrator.
- Main flow: feedback is saved with the active `SkillVector` version (FR-10.2). Once a role passes the feedback threshold, the EMA job writes a new weight version (FR-7.2 to 7.4). The administrator then exports a weights snapshot (FR-7.5), which ships inside the next core-engine release to every edition.

### UC7: "Match against a specific job description" (implemented)
- `POST /resumes/{id}/jd-match` : JD skills are dictionary matches against both taxonomies; score = 0.6 × coverage + 0.4 × embedding similarity; matched/missing lists and the closest catalogue role; deterministic, no LLM, nothing persisted. FR-8.1 and 8.2.

### UC13/UC14: admin taxonomy and dataset curation (planned)
- Today these are static JSON files. The plan is to make them DB-backed and editable without a deployment (FR-2.3), and later ESCO-based.

## Related documents

- [Data Flow Diagram](dfd.md)
- [Process Flow](process-flow.md)
- [Low-Level Design](lld.md): the API contracts behind each implemented use case
- [SRS v2.0](srs.md)
