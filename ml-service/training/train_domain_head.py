"""Trains a small classifier head for the job-field (domain) classifier on labelled resumes.

The app already embeds each resume's headline and its education-free opening with MiniLM
(services/domain_classifier.py). This script learns one softmax layer on top of those two vectors
from resumes labelled by Gemini (training/data_prep/gemini_label_domain.py), and saves it as a few
hundred KB of numbers (app/data/domain_head.npz) that the app applies with plain numpy: no new
dependency, nothing heavy at inference.

Run it on the GPU VM, not on a laptop (training/gcp-setup.md section 8). The MiniLM encoding uses
the GPU; the head itself is tiny. Out-of-fold probabilities are written next to the weights, so
the blend with the existing keyword and role evidence can be tuned afterwards without retraining.

    python -m training.train_domain_head --texts texts.jsonl --labels labels.jsonl --out-dir out/

texts.jsonl:  {"id": ..., "text": ...}        (the resume text as the app reads it)
labels.jsonl: gemini_label_domain.py output   (id, domain, confidence, ...)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

APP_DIR = Path(__file__).resolve().parents[1]


def features(texts: list[str]) -> np.ndarray:
    """[headline embedding | opening embedding] for each resume: the two vectors detect_domain uses."""
    sys.path.insert(0, str(APP_DIR))
    from app.services import domain_classifier, embeddings

    headlines = [domain_classifier._headline(t) or " " for t in texts]
    openings = [domain_classifier._snippet(t) or " " for t in texts]
    return np.concatenate([np.asarray(embeddings.embed(headlines)), np.asarray(embeddings.embed(openings))], axis=1)


def fit_head(x: np.ndarray, y: np.ndarray, n_classes: int, l2: float, epochs: int = 400, device: str = "cpu"):
    """Full-batch softmax regression with L2, trained with LBFGS. Returns (weights, bias) as numpy."""
    import torch

    xt = torch.tensor(x, dtype=torch.float32, device=device)
    yt = torch.tensor(y, dtype=torch.long, device=device)
    weights = torch.zeros(x.shape[1], n_classes, device=device, requires_grad=True)
    bias = torch.zeros(n_classes, device=device, requires_grad=True)
    optimiser = torch.optim.LBFGS([weights, bias], lr=1.0, max_iter=epochs, line_search_fn="strong_wolfe")

    def closure():
        optimiser.zero_grad()
        loss = torch.nn.functional.cross_entropy(xt @ weights + bias, yt) + l2 * (weights**2).sum()
        loss.backward()
        return loss

    optimiser.step(closure)
    return weights.detach().cpu().numpy(), bias.detach().cpu().numpy()


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def cross_validate(x, y, n_classes, l2, folds, seed, device):
    """Out-of-fold class probabilities. Folds are stratified where a class has enough resumes."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    fold_of = np.zeros(len(y), dtype=int)
    counters = {c: 0 for c in range(n_classes)}
    for index in order:  # round-robin per class keeps every class spread over the folds
        fold_of[index] = counters[y[index]] % folds
        counters[y[index]] += 1
    probabilities = np.zeros((len(y), n_classes))
    for fold in range(folds):
        train, test = fold_of != fold, fold_of == fold
        weights, bias = fit_head(x[train], y[train], n_classes, l2, device=device)
        probabilities[test] = softmax(x[test] @ weights + bias)
    return probabilities


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium",
                    help="drop labels the labeller was less sure of than this (default medium)")
    args = ap.parse_args()

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}")
    rank = {"low": 0, "medium": 1, "high": 2}

    with open(args.texts, encoding="utf-8") as handle:
        texts = {r["id"]: r["text"] for r in map(json.loads, filter(str.strip, handle))}
    with open(args.labels, encoding="utf-8") as handle:
        labels = [r for r in map(json.loads, filter(str.strip, handle)) if rank[r["confidence"]] >= rank[args.min_confidence]]
    labels = [r for r in labels if r["id"] in texts]
    domains = sorted({r["domain"] for r in labels})
    index = {d: i for i, d in enumerate(domains)}
    y = np.array([index[r["domain"]] for r in labels])
    print(f"{len(labels)} labelled resumes, {len(domains)} fields")

    x = features([texts[r["id"]] for r in labels])
    print(f"features {x.shape}")

    best = None
    for l2 in (1e-4, 3e-4, 1e-3, 3e-3, 1e-2):
        probabilities = cross_validate(x, y, len(domains), l2, args.folds, args.seed, device)
        accuracy = float((probabilities.argmax(axis=1) == y).mean())
        print(f"  l2={l2:g}: cross-validated accuracy {accuracy:.3f}")
        if best is None or accuracy > best[0]:
            best = (accuracy, l2, probabilities)
    accuracy, l2, probabilities = best

    weights, bias = fit_head(x, y, len(domains), l2, device=device)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out_dir / "domain_head.npz",
        weights=weights.astype(np.float32), bias=bias.astype(np.float32), domains=np.array(domains),
    )
    np.savez_compressed(args.out_dir / "oof.npz", ids=np.array([r["id"] for r in labels]),
                        probabilities=probabilities.astype(np.float32), domains=np.array(domains), y=y)
    report = {
        "date": date.today().isoformat(), "resumes": len(labels), "domains": domains, "l2": l2,
        "cross_validated_accuracy": round(accuracy, 4), "folds": args.folds, "min_confidence": args.min_confidence,
        "label_models": sorted({r["meta"]["model"] for r in labels}), "device": device,
        "class_counts": {d: int((y == index[d]).sum()) for d in domains},
    }
    (args.out_dir / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "class_counts"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
