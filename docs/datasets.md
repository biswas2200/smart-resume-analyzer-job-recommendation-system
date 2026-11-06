# Datasets for development, testing and training

Openly available datasets for this project, grouped by what we use them for. Licences are as the publishers stated them in September 2026 and must be re-checked before any dataset goes into the training corpus (FR-13.1). Nothing here is bundled in the repository; `ml-service/training/data/` will hold download and conversion scripts only.

The Use column means: Use now (development and golden tests), Training (the fine-tuning tracks in [Editions & Parity §5](editions-and-parity.md#5-fine-tuning)), or Reference (taxonomy or benchmark).

## 1. Resume corpora (parser and golden tests)

| Dataset | Size / format | Licence | Use | Notes |
|---|---|---|---|---|
| [Kaggle Resume Dataset (snehaanbhawal)](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset) | 2,400+ resumes from livecareer.com, PDF + text + HTML, 24 job categories | Check on page (Kaggle ToS) | Use now | The best source of real PDFs for `tests/golden/` and for `scripts/bench.py`. Categories give a weak label for role-matching sanity checks. |
| [Mehyaar/Annotated_NER_PDF_Resumes](https://huggingface.co/datasets/Mehyaar/Annotated_NER_PDF_Resumes) | 5,029 CVs, JSON `{text, annotations[start,end,SKILL]}`, 603 MB | MIT | Use now / Training A | Manually annotated IT skills. Fits the FR-1.7 dictionary-vs-NER recall tests and NER fine-tuning directly. |
| [Kaggle Resume NER Training Dataset (yashpwrr)](https://www.kaggle.com/datasets/yashpwrr/resume-ner-training-dataset) | ~22.5K samples, 25 BIO labels  | Not stated, verify | Training A | Same label schema as our current NER model, so it is the obvious continue-training set. |
| [DataTurks Resume Entities for NER](https://www.kaggle.com/datasets/dataturks/resume-entities-for-ner) | 220 annotated resumes, JSON | Public (Kaggle) | Training A / tests | Small but classic. Our NER model may have seen it in training, so use the unseen LiveCareer sample (`datasets/eval-unseen/`) alongside it. |
| [datasetmaster/resumes](https://huggingface.co/datasets/datasetmaster/resumes) | Real + synthetic resumes in JSON | Check on page | Use now | Ground-truth JSON makes it useful for parser regression tests. |
| [Divyaamith/Kaggle-Resume](https://huggingface.co/datasets/Divyaamith/Kaggle-Resume) | HF mirror of the Kaggle resume set | Check on page | Use now | Convenient `datasets.load_dataset` access. |
| [CareerCorpus](https://www.sciencedirect.com/science/article/pii/S2352340926001204) | Annotated resumes (Data in Brief, 2026) | Per article (typically CC BY 4.0) | Training A | Check the article's data-availability statement for the download link. |
| SynthResume (from [Layout-aware parsing](https://arxiv.org/pdf/2510.09722)) | 2,994 synthetic structured resumes with layout variation | Per paper | Training A | Useful for FR-1.6 sectioner tests on unusual layouts. |
| [Synthetic CVs for fairness testing](https://arxiv.org/pdf/2508.21179) | Synthetic CV generator | Per paper | Tests | Bias / counterfactual tests for the EU AI Act note in the SRS. |

## 2. Job descriptions and resume/JD pairs (matching and JD-match tests)

| Dataset | Size / format | Licence | Use | Notes |
|---|---|---|---|---|
| [cnamuangtoun/resume-job-description-fit](https://huggingface.co/datasets/cnamuangtoun/resume-job-description-fit) | Resume text, JD text, fit label (`Good/Potential/No fit`) | Check on page | Use now | The base set for FR-8.x JD matching and for ranking-quality regression of the embedder. |
| [0xnbk/resume-ats-score-v1-en](https://huggingface.co/datasets/0xnbk/resume-ats-score-v1-en) | Derived from the above with ATS-style scores | Check on page | Tests | A sanity comparison for our rule-based ATS rubric. We don't try to reproduce its scores. |
| [facehuggerapoorv/resume-jd-match](https://huggingface.co/datasets/facehuggerapoorv/resume-jd-match) | Resume/JD pairs | Check on page | Tests | |
| [jacob-hugging-face/job-descriptions](https://huggingface.co/datasets/jacob-hugging-face/job-descriptions) | Job descriptions with metadata | Check on page | Use now | Role catalogue expansion beyond the 20 or so curated roles. |
| [Kaggle: Resume and Job Description (sayyedfaizan95)](https://www.kaggle.com/datasets/sayyedfaizan95/resume-and-job-description) | Paired resumes and JDs | Check on page | Tests | |
| [LinkedIn Job Postings 2023–2024 (arshkon)](https://www.kaggle.com/datasets/arshkon/linkedin-job-postings) | ~124K postings with skills and salary tables | Check on page | Reference / Training B | Skill columns give role→skill co-occurrence for the weights snapshot and for embedder pairs. |
| [1.3M LinkedIn Jobs & Skills 2024 (asaniczka)](https://www.kaggle.com/datasets/asaniczka/1-3m-linkedin-jobs-and-skills-2024) | 1.3M postings + skills CSV | Check on page | Training B | Large; sample it. It is scraped data, so treat it as reference only for anything commercial. |

## 3. Skill and job-title benchmarks (embedder training and evaluation)

| Dataset | Size / format | Licence | Use | Notes |
|---|---|---|---|---|
| [TalentCLEF 2025 corpus (Zenodo)](https://zenodo.org/records/15240844) | Task A multilingual job-title matching (EN/ES/DE/ZH); Task B job-title → skills (EN) | Zenodo record (check) | Training B / eval | The published MNRL fine-tune recipes in [CEUR Vol-4038](https://ceur-ws.org/Vol-4038/paper_365.pdf) use this corpus. |
| [TalentCLEF 2026 corpus (Zenodo)](https://zenodo.org/records/19652670) | 2026 edition tasks | Zenodo record (check) | Training B / eval | Newer; use for held-out evaluation. |
| [SkillSpan](https://github.com/kris927b/SkillSpan) | 14.5K sentences, 12.5K hard/soft skill spans from job postings | See repo | Training A (skills) | Span-level skill extraction from the job-posting side, to go with the resume-side annotations. |
| [Skill-Extraction-benchmark (Decorte)](https://github.com/jensjorisdecorte/Skill-Extraction-benchmark/) | Skill mentions linked to ESCO ids | See repo | Eval | Measures taxonomy-linking quality once we move to ESCO. |
| [Tabiya livelihoods classifier](https://github.com/tabiya-tech/tabiya-livelihoods-classifier) | Code + data pointers for ESCO linking with MiniLM/mpnet | Apache-2.0 (check) | Training B | Reference implementation of the embedder recipe. |

## 4. Taxonomies (canonical skills and roles)

| Resource | Size / format | Licence | Use | Notes |
|---|---|---|---|---|
| [ESCO](https://esco.ec.europa.eu/en/use-esco/download) | ~3K occupations, ~14K skills, CSV/JSON-LD/RDF, 28 languages | Free for commercial and non-commercial reuse (EU Commission Decision 2011/833) | Use now / Reference | Replaces `skill_taxonomy.json` and `role_skills.json` in Phase 3. Its occupation→skill relations are a free source of (role, skill) pairs for Training B. |
| [Lightcast Open Skills](https://lightcast.io/open-skills) | 34K+ skills, API only (no static download) | Free API for non-profit/public good; check terms for commercial use | Reference | Larger tech vocabulary than ESCO. Being API-only, it can't serve the offline engine unless cached under licence. |
| [Nesta ojd_daps_skills](https://github.com/nestauk/ojd_daps_skills) | Library mapping extracted spans to ESCO or Lightcast | MIT | Reference / tooling | A ready-made ESCO mapper for the sectioner + dictionary stage. |

## 5. Suggested immediate test set (development now)

1. Golden fixtures (`ml-service/tests/golden/`): 40 PDFs from the Kaggle Resume Dataset (two per category, picked for layout variety) plus 10 synthetic edge cases (multi-column, no headings, skills-only, empty contact). Expected outputs are generated once per engine release and reviewed by hand.
2. Parser regression: 200 samples from `Mehyaar/Annotated_NER_PDF_Resumes` for skill recall, and 50 from DataTurks as an out-of-distribution check.
3. Matching sanity: on `cnamuangtoun/resume-job-description-fit`, assert that `Good fit` pairs score above `No fit` pairs on average. This is a ranking check with no absolute threshold.
4. Benchmark: `scripts/bench.py` runs the 40 golden PDFs and reports per-stage latency and peak RSS, which gives the NFR-1.3 numbers.

## 6. Licence checklist before training

- Record the licence text or URL for every dataset in `ml-service/training/DATASETS.md`.
- Kaggle datasets with no explicit licence are usable for development and evaluation. Do not ship their content, or a model trained on them, in a commercial edition until the licence is confirmed.
- Scraped job-board data (the LinkedIn sets) is reference-only for anything commercial.
- ESCO and MIT-licensed sets are safe for all editions.
