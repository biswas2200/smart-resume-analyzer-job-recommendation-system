# What the NER training data and models may be used for

Every source that goes into the trained NER model, with its licence or terms
as checked on 2026-10-09. Required by docs/datasets.md §6 before a trained
model ships. This is a record of what the sources state, not legal advice;
re-check before any commercial release.

| Source | Used for | Licence or terms | Commercial use |
|---|---|---|---|
| `yashpwr/resume-ner-bert` @ `3ea6ecf` | Teacher model, and the base the fine-tune starts from | Apache-2.0 (Hugging Face model card) | Allowed, with attribution and the licence notice |
| `distilbert/distilbert-base-cased` @ `6ea8117` | Student model | Apache-2.0 (Hugging Face model card) | Allowed, with attribution and the licence notice |
| LiveCareer Resume Dataset (Kaggle `snehaanbhawal/resume-dataset`) | 2,461 resumes, the bulk of the training text | CC0 Public Domain, as declared on Kaggle | Allowed as declared; but the resumes were collected from livecareer.com, and the uploader's CC0 cannot grant rights the uploader did not hold. Treat as a residual risk |
| DataTurks "Resume Entities for NER" (Kaggle `dataturks/resume-entities-for-ner`) | 110 training resumes (human labels), and the 110 test resumes | **Unknown** (Kaggle licence field) | **Not allowed until the licence is confirmed** (docs/datasets.md §6). The test resumes are only scored against, which is fine; a model trained on the 110 training resumes must not ship commercially while the licence is unknown |
| Gemini labels (`gemini-3.5-flash-lite` on Vertex AI) | The labels of the 2,461 LiveCareer resumes, and the skills of the 110 DataTurks training resumes | Google Cloud Service Specific Terms §17 and §20 (below) | **Open question**, see below |

## Gemini output as training labels

From the Google Cloud Service Specific Terms
(<https://cloud.google.com/terms/service-terms>), read 2026-10-09:

> **17. Use Restrictions for AI/ML Services.** a. Competitive Use. Customer
> will not, and will not allow End Users to use an AI/ML Service or Generated
> Output to develop a similar or competing product or service. [...]
> b. Model Restrictions. Customer will not, and will not allow End Users to,
> use output from an AI/ML Service (including Generated Output) to: (i)
> substitute, replace, or circumvent the use of a Google Model, directly or
> indirectly, or (ii) create or improve models similar to a Google Model.
> However, if an AI/ML Service offers the feature of fine-tuning or model
> distillation, Customer may use output from that AI/ML Service (including
> Generated Output) to modify and use Modified Google Models instead of Google
> Pre-Trained Models.

> **20. Generative AI Services.** a. [...] Generated Output is Customer Data.
> As between Customer and Google, Google does not assert any ownership rights
> in any new intellectual property created in the Generated Output.

How this bears on the project:

- §17(a) is unlikely to apply: a resume analyser does not compete with
  Google's AI services.
- §17(b)(ii) is unlikely to apply: a 66M-parameter BERT tagger is not similar
  to a Gemini model.
- **§17(b)(i) is the real question.** The local NER model is trained on
  Gemini's labels, and one of its aims is to extract resume fields locally
  instead of calling Gemini. That can be read as using Gemini output to
  "substitute [...] the use of a Google Model, directly or indirectly".

Options, for the owner to decide (ideally with legal advice):

1. Use the Gemini-trained model only for development and evaluation. Ship a
   model trained on human labels only.
2. Label the training resumes another way: by hand, or with a model whose
   terms allow training on its output.
3. Use Vertex AI's own tuning feature, which §17(b) explicitly allows. The
   result is then a Modified Google Model served on Vertex AI, not a local
   model.
4. Get written clarification from Google for this use.

Settled for this project: see the decision below.

## Decision (2026-10-10)

The owner decided: the project is non-commercial. It is not sold, and the
engineering domain, where the local NER model runs, is free for every user.
On that basis the trained models may ship in the app.

- **DataTurks:** 100 of its resumes are in the training set and 110 are the
  test set. With no commercial use, the unknown licence is accepted as a low
  risk. Re-check it if the project is ever sold.
- **LiveCareer:** CC0 as declared; no change.
- **Gemini labels:** §17(b)(i) has no exemption for non-commercial use, so
  this decision accepts that residual risk rather than removing it. If the
  project ever charges money, or Google asks, revisit options 1 to 4 above.
- **Scraped LinkedIn postings** (for the matcher, not the NER model): the same
  basis applies; research and non-commercial use only.
