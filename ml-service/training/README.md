# Model Training & Fine-Tuning on Google Cloud Platform (GCP)

> **Purpose:** Setup and execution guide for training, fine-tuning, and distilling models for Smart Resume Analyser and Job Recommendation System using GCP cloud compute resources (e.g., Compute Engine GPU VM or Vertex AI Workbench).

---

## 1. Why Train in the Cloud?

Consumer laptops typically lack the VRAM (GPU memory) and compute capability required to fine-tune transformer models like BERT and MiniLM without thermal throttling or out-of-memory errors. 

By leveraging **Google Cloud Platform (GCP)** and the allocated **$300 GCP credit**:
* We can spin up an on-demand virtual machine with an **NVIDIA T4 GPU (16 GB VRAM)** for only **~$0.35 / hour**.
* Training jobs finish in 15–30 minutes, costing under **$0.20 per run**.
* Training dependencies (such as CUDA-enabled PyTorch, Hugging Face `accelerate`, and `evaluate`) remain isolated in the cloud without bloating the local development environment or runtime production containers.

---

## 2. GCP Infrastructure Setup

> Data work comes before training: uploading the datasets, cleaning, and labelling
> the unlabelled resumes with `gemini-3.5-flash-lite` run on a CPU VM and BigQuery, described in
> [gcp-setup.md](gcp-setup.md); model choice and costs are in [data_prep/LABELLING.md](data_prep/LABELLING.md).
> The cleaning code and its checks are in [data_prep/](data_prep/README.md).
> This section covers the GPU VM used for training afterwards.

### Recommended Setup: Compute Engine VM with GPU
1. **Create an instance in GCP Console:**
   * **Machine family:** General-purpose / GPU (`n1-standard-4`, 4 vCPUs, 15 GB RAM).
   * **GPU:** 1 × NVIDIA T4 (16 GB GDDR6).
   * **Boot Disk:** Deep Learning on Linux (Debian with CUDA 12 pre-installed) — 50 GB Balanced Persistent Disk.
   * **Firewall / Access:** Allow default SSH access via `gcloud compute ssh`.

2. **Connect to the instance:**
   ```bash
   gcloud compute ssh --zone <your-zone> <instance-name>
   ```

3. **Clone the repository and install training requirements:**
   ```bash
   git clone <repo-url>
   cd smart-resume-analyzer-job-recommendation-system/ml-service
   python3 -m venv .venv-train
   source .venv-train/bin/activate
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
   pip install transformers datasets sentence-transformers accelerate evaluate seqeval onnx onnxruntime
   ```

---

## 3. Training Tracks

### Track A: Resume NER Continue-Training & Distillation
* **Teacher Model:** `yashpwr/resume-ner-bert` (BERT-base, 25 BIO labels, 431 MB; pinned `3ea6ecf`).
* **Student Model:** 6-layer `distilbert/distilbert-base-cased` (pinned `6ea8117`). Distillation compares teacher and student token by token, so the student must share the teacher's cased 28,996-token vocabulary, and this one does, byte for byte. Uncased students (`distilbert-base-uncased`, `MiniLM-L6-H384-uncased`) split text differently from the first token (107 vs 91 tokens on the first 400 characters of a DataTurks resume) and drop capitalisation, which names and employers depend on.
* **Objective:** Knowledge distillation combining:
  $$\mathcal{L} = \alpha \cdot \text{KL}(\text{student}, \text{teacher}) + (1 - \alpha) \cdot \text{CrossEntropy}(\text{labels})$$
* **Outcome:** Reduces the NER model from 107.7M to 65.2M parameters, 431 MB to 261 MB in fp32 (int8 quantization at export shrinks it further; measure it then), and must **beat the measured baseline**: 60 % field macro F1 on the DataTurks held-out half and 64 % on the unseen LiveCareer sample (`supporting-docs/ml-pipeline.md`).

#### Track A run order (on the GPU VM)

Code: `data_prep/training_set.py` (step 2), `train_ner.py` (step 3),
`label_quality.py` (the label-quality classifier) and `evaluate_model.py`.
Each step's output goes to the bucket before the next starts. Stop at any
failed gate.

| # | Step | Gate before going on |
|---|---|---|
| 0 | `evaluate_model.py` with no trained models: re-scores the app's model in this harness | reproduces the 60 % DataTurks baseline; otherwise the harness is wrong and nothing after it can be trusted |
| 1 | `training_set.py skill-inputs`, then `gemini_label.py` on those 110 DataTurks train/dev resumes (dry run, then about $0.30, cap $1) | cost as estimated; `not_in_text` near 0 |
| 2 | `training_set.py build` | `report.json`: no test resume in train or dev; label counts as expected |
| 3 | Any training mode with `--max-steps 30 --usd-per-hour <VM price>` | the projected cost of the planned run is reported to the user before the full run (standing cost rule) |
| 4 | `train_ner.py finetune`: the teacher on the full training set | dev entity F1 rises across epochs |
| 5 | Label-quality rounds (at most 3): `train_ner.py folds --k 3`, then `label_quality.py`, then a person reads `review.md`, then retrain with `--exclude` | keep a round only if dev F1 improves; stop at the first round that does not, or when 15 % of the set has been removed |
| 6 | `train_ner.py distill --teacher <best teacher>` | dev F1 close to the teacher's |
| 7 | `evaluate_model.py <teacher> <student>` on DataTurks test and the unseen 20 | beats 60 % and 64 % in the same run as the baseline. The test sets are used only here, once, never to pick between rounds |

### Track B: Skill & Role Embedder Fine-Tuning
* **Base Model:** `sentence-transformers/all-MiniLM-L6-v2` (22.7M parameters).
* **Training Data:** Title-to-skill pairs and occupation-skill pairs from `app/data/role_skills.json` and LinkedIn datasets.
* **Loss Function:** `MultipleNegativesRankingLoss` (MNRL).
* **Outcome:** Enhances domain-specific semantic similarity between candidate skill variants and career role descriptions (+4.3% mAP).

---

## 4. Exporting Trained Models for Production

Once training completes and validation checks pass (held-out F1 not below previous baseline):
1. **Export to ONNX:**
   ```bash
   python -m transformers.onnx --model=./trained_ner/ --feature=token-classification ./exported_models/ner.onnx
   ```
2. **Compute Content Hash:**
   ```bash
   sha256sum ./exported_models/ner.onnx > ./exported_models/ner.onnx.sha256
   ```
3. **Deploy Artifact:**
   Copy the exported ONNX model and updated SHA hash into the production ML service configuration (`app/config.py`).
