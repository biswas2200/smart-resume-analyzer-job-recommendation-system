# Data flow diagram (DFD)

Drawn in Gane and Sarson notation: rounded processes, external entities and parallel-line data stores. Level 0 shows the system boundary. Level 1 breaks down the analysis pipeline and the backend loop. `*` marks processes and stores that are still planned in the [implementation order](editions-and-parity.md#7-implementation-order).

## Level 0: context diagram

```mermaid
flowchart LR
    Candidate["Candidate"]
    Admin["System Administrator"]
    LLM["Google Vertex AI (Gemini 2.5 Flash Lite)\n(narrative only)"]

    SYS(("0\nSmart Resume Analyser and Job Recommendation System"))

    Candidate -->|PDF resume, feedback, JD text| SYS
    SYS -->|profile, matches, gaps, ATS score,\nexplanation, engine_fingerprint| Candidate
    Admin -->|taxonomy, role dataset,\nrecompute, snapshot export, model release| SYS
    SYS -.->|explanation prompt;\nextraction prompt (non-eng)| LLM
    LLM -.->|narrative; structured JSON| SYS
```

## Level 1: the analysis pipeline (process 0, inside the core engine)

```mermaid
flowchart TB
    Caller["Backend Service (Spring Boot)"]
    LLM["Google Vertex AI (Gemini)"]

    P0(("0.5\nExtract Text\n(document_extraction/)"))
    P05(("0.7\nSegment Sections*\n(sectioner.py)"))
    P1(("1.0\nExtract Entities\n(dictionary_skills.py* +\nlocal_ner_parser.py)"))
    P2(("2.0\nNormalize Skills\n(normalizer.py)"))
    P3(("3.0\nMatch Roles\n(matcher.py: vector lookup*,\nweighted mean*, round 2dp*)"))
    P4(("4.0\nScore ATS\n(ats_score.py)"))
    P5(("5.0\nAnalyze Gaps\n(gap_analysis.py)"))
    P6(("6.0\nExplain\n(template* | llm)"))
    P7(("6.5\nStamp Fingerprint*\n(config.py)"))

    D1[("D1: Skill Taxonomy\nskill_taxonomy.json")]
    D2[("D2: Role Dataset\nrole_skills.json")]
    D7[("D7: Vector tables*\nskill_vectors.npy, role_vectors.npy")]
    D8[("D8: Weights snapshot*\nweights_snapshot.json")]
    D9[("D9: Pinned models\nNER (ONNX*), MiniLM")]

    Caller -->|PDF| P0
    P0 -->|resume_text| P05
    P05 -->|sections| P1
    P0 -->|resume_text| P4
    P1 <-->|variants| D1
    P1 <-->|model| D9
    P1 -.->|extraction prompt, opt-in| LLM
    P1 -->|ResumeProfile + skill spans| P2
    P2 <-->|variant → canonical| D1
    P2 -->|canonical skills| P3
    P3 <-->|role skill lists| D2
    P3 <-->|vectors| D7
    P3 <-->|weights| D8
    P3 -.->|unknown skills only| D9
    P3 -->|RoleMatch[]| P5
    P3 -->|RoleMatch[]| P6
    P4 -->|AtsScoreResponse| P6
    P5 -->|GapAnalysis[]| P6
    P1 -->|ResumeProfile| P6
    P6 -.->|prompt, explainer=llm| LLM
    LLM -.->|narrative| P6
    P6 --> P7
    P7 -->|AnalyzeResponse\n+ engine_fingerprint| Caller
```

## Level 1: backend loop (implemented; snapshot export planned)

```mermaid
flowchart TB
    Candidate["Candidate"]
    Admin["Administrator"]
    MLPipeline(("0.0\nAnalysis pipeline\n(above)"))
    P8(("7.0\nUpload & Persist\n(resume.ResumeService)"))
    P9(("8.0\nCollect Feedback\n(feedback.FeedbackService)"))
    P10(("9.0\nEMA Update\n(skillvector.SkillVectorService)"))
    P11(("10.0\nExport Snapshot*"))

    D3[("D3: resumes, parsed_profiles\n(PostgreSQL) + files (MinIO)")]
    D4[("D4: recommendations")]
    D5[("D5: skill_vectors (versioned)")]
    D6[("D6: feedback")]
    D8[("D8: weights_snapshot.json\n(ships in next release)")]

    Candidate -->|PDF| P8
    P8 -->|file, top_n| MLPipeline
    MLPipeline -->|AnalyzeResponse| P8
    P8 --> D3
    P8 --> D4
    Candidate -->|helpful / not helpful| P9
    P9 --> D6
    P9 -->|threshold reached| P10
    D5 <--> P10
    P10 -->|new_weight = α·signal + (1−α)·old| D5
    Admin --> P11
    D5 --> P11
    P11 --> D8
```

## Notes

- `D1`/`D2` are flat JSON files today. FR-2.3 (admin-editable taxonomy) and the ESCO migration will move them to versioned, DB-backed stores. Either way they are hashed into the engine fingerprint.
- `D7`, `D8` and `D9` make results reproducible. They ship as constants inside the release artifact and are identical in every edition.
- `D5` implements SRS §3.7. `D8` is its frozen, per-release export (FR-7.5), which lets the weights learned on the web reach Community users without a network dependency.

## Related documents

- [Use Case Diagram](use-case-diagram.md) · [Process Flow](process-flow.md) · [Entity Diagram](entity-diagram.md) · [Editions & Parity](editions-and-parity.md)
