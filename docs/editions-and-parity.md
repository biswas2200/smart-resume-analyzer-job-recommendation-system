# Result determinism and parity

> Design reference for core engine determinism, reproducible scoring across deployments, and the cloud web app. The requirements are in [SRS §3.11 to 3.13](srs.md#311-core-engine-architecture-and-result-parity-revised-in-v22).  
> The historical offline Community Edition Docker and CLI design is archived in [`docs/archive/community-edition.md`](archive/community-edition.md).

## 1. The promise and how it is kept

> For the same Engineering & Technology resume and the same `engine_fingerprint`, any deployment of the core engine returns byte-identical `profile`, `ats_score`, `matches` and `gaps`.

The determinism promise is scoped to the domain the local deterministic engine serves. Other fields run on Google Vertex AI (Gemini via ADC); on the web every account may use them, with an optional operator budget (`LLM_DAILY_BUDGET_USD`). Nothing about that changes the engineering score path.

This holds because one versioned core-engine artifact handles scoring, and every non-deterministic or paid feature sits above the score, never inside it. Three other products split their editions the same way:

- SonarQube Community vs Cloud: the same engine and rule set produce the same findings; paid editions add analyzers and never change existing ones.
- Semgrep Community vs Pro: the open-source engine is identical to Pro for the scope it covers (single-file analysis); Pro adds cross-file layers and openly documents where results may differ.
- Plane Community vs Commercial: Community Edition is at par with the cloud web app; the Commercial edition is built on top of it.

```mermaid
flowchart TB
    subgraph CORE["Core engine — one artifact per release tag"]
        direction LR
        X["extract\n(pdfplumber)"] --> S["segment\n(headings)"] --> D["dictionary skills\n(Aho-Corasick)"] --> N["NER\n(edu/exp only)"] --> M["match\n(vector lookup)"] --> A["ATS rules"] --> T["template\nexplanation"]
    end
    FP["engine_fingerprint =\n{engine_version, ner_sha, embed_sha,\ntaxonomy_sha, weights_snapshot_id}"]
    CORE --- FP
    W["Cloud web app
accounts, full history
+ LLM narrative, 5 roles
+ every field read locally"]
    CORE --> W
    W -.->|HTTPS (ADC): narrative only| LLM[["Google Vertex AI (Gemini)"]]
    style CORE fill:#eef6ff,stroke:#4a7dbd
```

Rules that follow from the diagram:

1. Same artifact. Every deployment embeds the same models (by content hash), taxonomy, vector table and weights snapshot.
2. The score path is model-pinned and deterministic. Nothing on the score path is downloaded at runtime or calls an external LLM.
3. Added features only add columns. The LLM narrative, reranker and live weights are separate, labelled fields. If live weights are used, the response says so.
4. A fingerprint on every response, so anyone can check they got the same engine.
5. A golden suite gate. A release ships only if the same fixtures produce identical outputs against the deployed API.

## 2. What had to change in the code

Three things in the ML service (as of commit `9f8b7a0`) break parity:

| Problem | Where | Fix |
|---|---|---|
| Explanation always calls Groq/Gemini; no API key means no result, and LLM outputs are not reproducible | `app/services/explainer.py` | `TemplateExplainer` is the default; `EXPLAINER_BACKEND=llm` is opt-in |
| Models are downloaded unpinned from HuggingFace at first run | `app/services/embeddings.py`, `app/services/local_ner_parser.py` | Pin `revision=<sha>`, export to ONNX, bake into the image, hash into the fingerprint |
| Scores rounded to 4 dp after sorting; cross-CPU drift (~1e-5) can flip near-ties | `app/services/matcher.py` | Round to 2 dp before sorting, tie-break by role name |

## 3. Restaged pipeline (why it fits on a small PC)

The current pipeline runs the BERT-base NER model over the whole resume in 380-word chunks (3 or 4 passes for two pages) and embeds every candidate and role skill with MiniLM on every request. Two observations make it much lighter:

- The matcher only compares skills that were normalized to the finite taxonomy, so every skill vector and role vector can be precomputed at build time and shipped as a lookup table (taxonomy × 384 floats, under 1 MB). The embedding model leaves the hot path, and because the vectors are shipped constants, floating-point drift leaves the matcher too.
- Only Experience and Education need the NER model. Skills are better found by dictionary matching against the taxonomy (deterministic, linear time), and contact details are already regex.

| Stage | What | Cost on a 2-core PC |
|---|---|---|
| 1 Extract | pdfplumber | < 0.3 s |
| 2 Segment | heading regex → Skills / Experience / Education / other (fallback: whole text) | ≈ 0 |
| 3 Contact | email / phone regex | ≈ 0 |
| 4 Skills | Aho-Corasick over `skill_taxonomy.json` + NER "Skills" spans for recall | < 20 ms |
| 5 NER | BERT on Experience + Education only, batch 1, 2 threads | 1 or 2 chunks × 0.3 to 1 s |
| 6 Match | `skill_vectors.npy` / `role_vectors.npy` lookup; MiniLM only for out-of-taxonomy skills | < 10 ms |
| 7 ATS | integer rules | ≈ 0 |
| 8 Explain | template (LLM optional) | ≈ 0 |

Expected on the minimum spec: 1 to 3 s per two-page resume and ≈ 1 to 1.5 GB peak RAM. These are estimates until `scripts/bench.py` reports measured numbers (NFR-1.3). Optional `ENGINE_IDLE_UNLOAD_SECONDS` unloads the NER model when idle so Community stays under 300 MB between runs.

## 4. Cloud infrastructure specifications and costs (Google Cloud Platform)

The stack runs on Google Cloud Platform within the user's $300 GCP credit:

| Environment | Target GCP specification | Estimated cost (Sept 2026) | Purpose |
|---|---|---|---|
| App stack VM (Option A) | Compute Engine `e2-standard-4` (4 vCPU, 16 GB RAM) | ~$48 / month (or `e2-medium` at $24.46 / mo) | Runs Docker Compose: Frontend, Backend, ML Service, PostgreSQL, MinIO |
| Model training and fine-tuning | Compute Engine / Vertex AI Workbench with NVIDIA T4 GPU | ~$0.35 / hour | Distillation & continue-training runs (e.g. 2 hrs ≈ $0.70) |
| Google Vertex AI (`gemini-2.5-flash-lite`) | Cloud API (ADC authentication) | ~$0.00008 per analysis (narrative only) | Narrative coaching; the opt-in extraction path is ~$0.00028 |
| Domain and TLS | Cloud DNS + Let's Encrypt | ~$10 / year, TLS free | Production ingress |

The historical local PC hardware baseline for the offline edition is in [Archived: Community Edition](archive/community-edition.md).

## 5. Fine-tuning on Google Cloud

Local consumer hardware doesn't have the VRAM or compute, so fine-tuning and distillation run on GCP GPU instances (Compute Engine with NVIDIA T4, or Vertex AI Workbench).

| Track | Model | Tooling | Data | Compute | Outcome |
|---|---|---|---|---|---|
| A. NER (first) | Continue-train `yashpwr/resume-ner-bert`, then distil into a 6-layer student (DistilBERT or MiniLM-L6-H384) | HF `Trainer`, token classification; distillation = KL(student, teacher) + CE(labels) | See [Datasets §1](datasets.md#1-resume-corpora-parser-and-golden-tests); unlabelled LiveCareer resumes labelled offline by `gemini-3.5-flash-lite` (`ml-service/training/data_prep/LABELLING.md`) | ≈ 15 to 20 min on GCP T4 GPU (< $0.20) | NER model from 431 MB to ≈ 130 MB fp32 (≈ 35 MB int8), beating the current baseline (60 % / 64 % field macro F1, see `supporting-docs/ml-pipeline.md` (section "NER model baseline")) |
| B. Embedder | `all-MiniLM-L6-v2` | `SentenceTransformerTrainer` + `MultipleNegativesRankingLoss` | ESCO occupation→skill pairs, TalentCLEF title pairs, taxonomy variants | minutes on GCP T4 GPU | +4.3 % mAP on title matching; vectors precomputed for runtime lookup |
| C. Optional decoder | Qwen3-0.6B LoRA for extraction or narrative | Soup or TRL, export GGUF/ONNX | Own instruction set | ~1 hr on GCP T4 GPU | Fast layout-aware extraction |

Training runs in `ml-service/training/` on GCP, and its outputs are hashed ONNX artifacts deployed in the production ML service image.

## 6. Research behind the design

Sources matching the problem at 65 % or better, and what each one contributes:

| Source | Match | What we take |
|---|---|---|
| [SonarQube Cloud vs Server](https://www.sonarsource.com/blog/sq-sc_guidance/) | 90 % | Same engine + same rule pack ⇒ same findings |
| [Semgrep CE vs Pro](https://semgrep.dev/docs/semgrep-pro-vs-oss), [Doyensec comparison](https://www.doyensec.com/resources/Comparing_Semgrep_Pro_and_Community_Whitepaper.pdf) | 85 % | Core engine identical for its scope; Pro adds layers; disclose differences |
| [Plane editions](https://developers.plane.so/self-hosting/editions-and-versions) | 80 % | Open core at par with Cloud Free; Commercial built on top |
| [Resume-Matcher](https://github.com/srbhr/Resume-Matcher) | 65 % | Deterministic matching keeps scores reproducible; avoid LLM scoring drift |
| [PyTorch AVX512 reproducibility issue](https://github.com/pytorch/pytorch/issues/155552), [PyTorch reproducibility notes](https://docs.pytorch.org/docs/main/notes/randomness.html) | 90 % | ~1e-5 drift across CPUs; no cross-hardware guarantee ⇒ round + tie-break |
| [Thinking Machines: Defeating Nondeterminism](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/), [HEAL](https://arxiv.org/pdf/2606.21023) | 70 % | LLM outputs change with batch size and hardware ⇒ keep LLMs off the score path |
| [Same Input, Different Scores](https://arxiv.org/abs/2603.04417), [AutoScreen-FW](https://arxiv.org/pdf/2603.18390) | 85 % | LLM judges disagree with themselves at temperature 0; keep scoring rule-based |
| [Vespa: Embedding tradeoffs quantified](https://blog.vespa.ai/embedding-tradeoffs-quantified/) | 75 % | Quantization costs 2 to 13 %; ship one consistent precision everywhere |
| [Meta HierCat](https://arxiv.org/pdf/2302.10527) | 80 % | Precompute the finite side of the match |

## 7. Implementation order

0. Documentation refresh (this page, [SRS v2.0](srs.md), [Datasets](datasets.md), all design docs): done.
1. Core engine self-contained: template explainer, pinned ONNX models, 2-dp rounding, `engine_fingerprint`.
2. Restaged pipeline: sectioner, dictionary skills, NER on two sections, precomputed vector tables.
3. Weights snapshot: admin export endpoint; engine consumes the snapshot.
4. GCP cloud deployment and Community Edition archiving: done ([archive](archive/community-edition.md)).
5. (Removed in v2.14: there is one version of the product, so no tier gating.)
6. Golden parity suite in CI.
7. Cloud training pipeline (`ml-service/training/`) on GCP with GPU, plus a benchmark script.
8. Later: ESCO taxonomy migration.

## Related documents

- [SRS v2.0](srs.md) · [Datasets](datasets.md) · [System Architecture](architecture.md) · [HLD](hld.md) · [LLD](lld.md)
