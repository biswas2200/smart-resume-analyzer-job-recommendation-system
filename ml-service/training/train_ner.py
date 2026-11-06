"""Trains the resume NER model on the BIO files from data_prep/training_set.py.
A plain PyTorch loop, so every step can be followed in a debugger. Runs on the
GPU VM (gcp-setup.md §8), never on the laptop.

    cd ml-service
    # A. continue-train the app's model (the teacher) on the new data:
    python -m training.train_ner finetune --data TRAINING_DIR --out OUT/teacher
    # B. distil it into the 6-layer cased student:
    python -m training.train_ner distill --data TRAINING_DIR --teacher OUT/teacher --out OUT/student
    # C. k-fold predictions for the label-quality classifier (label_quality.py):
    python -m training.train_ner folds --data TRAINING_DIR --k 3 --out OUT/folds
    # any mode: --max-steps 30 --usd-per-hour 0.45 measures speed and projects the full run's cost

Words in the BIO files are split into the model's subwords here; only a word's
first subword carries its label (the rest are -100, ignored by the loss), and
long resumes are cut into 512-token windows that overlap by 128 tokens.
Models and settings come from training/config.py.
"""

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

from training.config import ner_config
from training.data_prep.schema import LABEL_LIST

IGNORE = -100
LABEL2ID = {label: i for i, label in enumerate(LABEL_LIST)}


# --- pure helpers (unit-tested without a GPU) -------------------------------------


def encode(row: dict, tokenizer, max_length: int = 512, stride: int = 128) -> list[dict]:
    """Model inputs for one BIO row: one dict per window, labels on first subwords only."""
    enc = tokenizer(row["tokens"], is_split_into_words=True, truncation=True, max_length=max_length,
                    stride=stride, return_overflowing_tokens=True)
    windows = []
    for w in range(len(enc["input_ids"])):
        labels, previous = [], None
        for word in enc.word_ids(w):
            if word is None or word == previous:
                labels.append(IGNORE)
            else:
                labels.append(LABEL2ID[row["ner_tags"][word]])
            previous = word
        windows.append({"input_ids": enc["input_ids"][w], "attention_mask": enc["attention_mask"][w],
                        "labels": labels, "word_ids": enc.word_ids(w)})
    return windows


def kd_loss(student_logits, teacher_logits, labels, temperature: float, alpha_ce: float, alpha_kd: float):
    """Cross-entropy on the gold labels plus KL divergence to the teacher's
    softened distribution (scaled by T², Hinton et al. 2015), both over the
    labelled positions only."""
    import torch.nn.functional as F

    mask = labels != IGNORE
    s, t = student_logits[mask], teacher_logits[mask]
    ce = F.cross_entropy(s, labels[mask])
    kd = F.kl_div(F.log_softmax(s / temperature, -1), F.softmax(t / temperature, -1),
                  reduction="batchmean") * temperature ** 2
    return alpha_ce * ce + alpha_kd * kd


def spans(tags: list[str]) -> set[tuple[int, int, str]]:
    """(start, end, type) entity spans of a BIO sequence; an I- without a
    matching opener starts a new span, as seqeval's default does."""
    found, start, kind = set(), None, None
    for i, tag in enumerate([*tags, "O"]):
        if tag == "O" or tag.startswith("B-") or (tag.startswith("I-") and tag[2:] != kind):
            if start is not None:
                found.add((start, i, kind))
            start, kind = (i, tag[2:]) if tag != "O" else (None, None)
    return found


def entity_f1(gold: list[list[str]], pred: list[list[str]]) -> dict:
    """Exact-span micro precision, recall and F1, overall and per type."""
    hits, n_gold, n_pred = {}, {}, {}
    for g, p in zip(gold, pred):
        gs, ps = spans(g), spans(p)
        for _, _, k in gs:
            n_gold[k] = n_gold.get(k, 0) + 1
        for _, _, k in ps:
            n_pred[k] = n_pred.get(k, 0) + 1
        for _, _, k in gs & ps:
            hits[k] = hits.get(k, 0) + 1

    def prf(h, p, g):
        precision, recall = (h / p if p else 0.0), (h / g if g else 0.0)
        return {"precision": precision, "recall": recall,
                "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}

    result = {k: prf(hits.get(k, 0), n_pred.get(k, 0), n_gold[k]) for k in sorted(n_gold)}
    result["overall"] = prf(sum(hits.values()), sum(n_pred.values()), sum(n_gold.values()))
    return result


def merge_window_probs(n_words: int, windows: list[tuple[list, list]]) -> list[list[float] | None]:
    """Per-word label probabilities from overlapping windows: each window gives
    (word_ids, per-token probabilities); a word seen in several windows gets
    the average of its first-subword probabilities."""
    sums, counts = [None] * n_words, [0] * n_words
    for word_ids, probs in windows:
        previous = None
        for word, p in zip(word_ids, probs):
            if word is not None and word != previous:
                sums[word] = list(p) if sums[word] is None else [a + b for a, b in zip(sums[word], p)]
                counts[word] += 1
            previous = word
    return [None if s is None else [x / c for x in s] for s, c in zip(sums, counts)]


# --- training (needs torch; run on the GPU VM) ------------------------------------


def read_bio(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _batches(windows, batch_size, tokenizer, shuffle, seed=0):
    import torch

    order = list(range(len(windows)))
    if shuffle:
        random.Random(seed).shuffle(order)
    for i in range(0, len(order), batch_size):
        chunk = [windows[j] for j in order[i:i + batch_size]]
        width = max(len(w["input_ids"]) for w in chunk)
        pad = lambda key, value: torch.tensor([w[key] + [value] * (width - len(w[key])) for w in chunk])
        yield {"input_ids": pad("input_ids", tokenizer.pad_token_id), "attention_mask": pad("attention_mask", 0),
               "labels": pad("labels", IGNORE)}


def predict_tags(model, tokenizer, rows, device, batch_size=16, probabilities=False):
    """Tags (or per-word probabilities) for whole resumes, windows merged."""
    import torch

    model.eval()
    out = []
    with torch.no_grad():
        for row in rows:
            windows = encode(row, tokenizer)
            pairs = []
            for batch_start in range(0, len(windows), batch_size):
                chunk = windows[batch_start:batch_start + batch_size]
                batch = next(_batches(chunk, len(chunk), tokenizer, shuffle=False))
                logits = model(input_ids=batch["input_ids"].to(device),
                               attention_mask=batch["attention_mask"].to(device)).logits
                probs = torch.softmax(logits.float(), -1).cpu().tolist()
                pairs += [(w["word_ids"], p[:len(w["input_ids"])]) for w, p in zip(chunk, probs)]
            word_probs = merge_window_probs(len(row["tokens"]), pairs)
            if probabilities:
                out.append(word_probs)
            else:
                out.append([LABEL_LIST[max(range(len(p)), key=p.__getitem__)] if p else "O" for p in word_probs])
    return out


def train(mode: str, train_rows, dev_rows, out_dir: Path, *, teacher_dir=None, epochs=None,
          max_steps=None, usd_per_hour=None, seed=13) -> dict:
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, get_linear_schedule_with_warmup

    cfg = ner_config
    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    labels = {"num_labels": len(LABEL_LIST), "id2label": dict(enumerate(LABEL_LIST)), "label2id": LABEL2ID}
    if mode == "distill":
        name, revision = cfg.student_model, cfg.student_model_revision
    else:
        name, revision = cfg.base_model, cfg.base_model_revision
    tokenizer = AutoTokenizer.from_pretrained(name, revision=revision)
    model = AutoModelForTokenClassification.from_pretrained(name, revision=revision, **labels).to(device)
    teacher = None
    if mode == "distill":
        teacher = AutoModelForTokenClassification.from_pretrained(teacher_dir).to(device).eval()

    windows = [w for row in train_rows for w in encode(row, tokenizer, cfg.max_seq_length)]
    epochs = epochs or cfg.num_epochs
    steps_per_epoch = math.ceil(len(windows) / cfg.batch_size)
    total = max_steps or steps_per_epoch * epochs
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate, weight_decay=0.01)
    schedule = get_linear_schedule_with_warmup(optimizer, int(0.1 * total), total)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    print(f"{mode}: {len(train_rows)} resumes, {len(windows)} windows, {steps_per_epoch} steps/epoch, "
          f"{total} steps on {device}", flush=True)

    best, history, step, started = -1.0, [], 0, time.monotonic()
    for epoch in range(epochs):
        model.train()
        for batch in _batches(windows, cfg.batch_size, tokenizer, shuffle=True, seed=seed + epoch):
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast(device_type=device, dtype=torch.float16, enabled=device == "cuda"):
                outputs = model(**batch)
                if teacher is None:
                    loss = outputs.loss
                else:
                    with torch.no_grad():
                        teacher_logits = teacher(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).logits
                    loss = kd_loss(outputs.logits.float(), teacher_logits.float(), batch["labels"],
                                   cfg.temperature, cfg.alpha_ce, cfg.alpha_kd)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            schedule.step()
            step += 1
            if step % 50 == 0 or step == max_steps:
                print(f"  step {step}/{total} loss {loss.item():.4f}", flush=True)
            if max_steps and step >= max_steps:
                seconds = (time.monotonic() - started) / step
                full = seconds * steps_per_epoch * epochs / 3600
                report = {"seconds_per_step": seconds, "projected_hours": full,
                          "projected_usd": full * usd_per_hour if usd_per_hour else None}
                print("measured:", json.dumps(report), flush=True)
                return report
        if dev_rows:
            gold = [r["ner_tags"] for r in dev_rows]
            scores = entity_f1(gold, predict_tags(model, tokenizer, dev_rows, device))
            history.append({"epoch": epoch + 1, "dev": scores["overall"]})
            print(f"epoch {epoch + 1}: dev entity F1 {scores['overall']['f1']:.4f}", flush=True)
            if scores["overall"]["f1"] > best:
                best = scores["overall"]["f1"]
                model.save_pretrained(out_dir)
                tokenizer.save_pretrained(out_dir)
                (out_dir / "dev_scores.json").write_text(json.dumps(scores, indent=2))
    if not dev_rows:
        model.save_pretrained(out_dir)
        tokenizer.save_pretrained(out_dir)
    summary = {"mode": mode, "best_dev_f1": best, "history": history, "steps": step,
               "hours": (time.monotonic() - started) / 3600, "base": f"{name}@{revision}"}
    (out_dir / "train_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def folds(rows, k: int, out_dir: Path, **kwargs) -> None:
    """Out-of-fold per-word probabilities: each resume is scored by a model
    trained on the other k-1 folds, so it never saw that resume's labels."""
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    order = sorted(rows, key=lambda r: r["id"])
    random.Random(7).shuffle(order)
    with open(out_dir / "oof_probs.jsonl", "w", encoding="utf-8") as handle:
        for fold in range(k):
            held = order[fold::k]
            held_ids = {r["id"] for r in held}
            fold_dir = out_dir / f"fold{fold}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            train("finetune", [r for r in order if r["id"] not in held_ids], [], fold_dir, **kwargs)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = AutoModelForTokenClassification.from_pretrained(fold_dir).to(device)
            tokenizer = AutoTokenizer.from_pretrained(fold_dir)
            for row, probs in zip(held, predict_tags(model, tokenizer, held, device, probabilities=True)):
                handle.write(json.dumps({"id": row["id"], "fold": fold, "probs": [
                    [round(x, 4) for x in p] if p else None for p in probs]}) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=["finetune", "distill", "folds"])
    parser.add_argument("--data", type=Path, required=True, help="training_set.py output folder")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, help="fine-tuned teacher folder (distill)")
    parser.add_argument("--k", type=int, default=3, help="number of folds (folds)")
    parser.add_argument("--exclude", type=Path, help="file of resume ids to leave out (label_quality.py output)")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--max-steps", type=int, help="stop after N steps and project the full run's time and cost")
    parser.add_argument("--usd-per-hour", type=float, help="VM price, for the projection")
    args = parser.parse_args()
    if args.mode == "distill" and not args.teacher:
        parser.error("distill needs --teacher")

    excluded = set(args.exclude.read_text().split()) if args.exclude else set()
    train_rows = [r for r in read_bio(args.data / "bio/train.jsonl") if r["id"] not in excluded]
    dev_rows = read_bio(args.data / "bio/dev.jsonl")
    args.out.mkdir(parents=True, exist_ok=True)
    kwargs = {"epochs": args.epochs, "max_steps": args.max_steps, "usd_per_hour": args.usd_per_hour}
    if args.mode == "folds":
        folds(train_rows, args.k, args.out, **kwargs)
    else:
        print(json.dumps(train(args.mode, train_rows, dev_rows, args.out, teacher_dir=args.teacher, **kwargs), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
