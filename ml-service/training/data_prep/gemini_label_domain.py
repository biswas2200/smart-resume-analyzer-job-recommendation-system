"""Labels resumes with the job FIELD they belong to (one of data/domains.json's 23
domains), using Gemini on Vertex AI, so the domain classifier can be measured and trained
against real answers instead of the LiveCareer folder names (which are loose: the
"HEALTHCARE" folder holds pharma sales reps and BI analysts).

The resumes are read the way the app reads them: PDFs go through the app's own text extractor.
Each answer has a field, an optional second field, the job title the resume is aimed at, a
confidence and a one-sentence reason (the reason is what makes a by-eye audit quick).

    cd ml-service
    export GOOGLE_CLOUD_PROJECT=smart-resume-analyzer-a7x2       # or ml-service/.env
    P="--pdf-dir ../datasets/archive/data/data --out ../datasets/labelled/domains.gemini-3.8-flash.v1.jsonl"
    # 1. estimate first, no API call (cost rule):
    python -m training.data_prep.gemini_label_domain $P --per-category 5 --dry-run
    # 2. a small real sample, then compare assumed with actual:
    python -m training.data_prep.gemini_label_domain $P --per-category 5 --limit 6 --max-usd 0.25
    # 3. audit the answers by eye (see LABELLING.md), then the real run:
    python -m training.data_prep.gemini_label_domain $P --per-category 25 --max-usd 4

Re-running continues where it stopped (resumes already in --out are skipped), and a larger
--per-category extends the same sample (the per-category shuffle is seeded), so nothing is paid
for twice. The labelled files are git-ignored (the resumes are licensed for non-commercial use).
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "gemini-3.8-flash"
# Characters of resume text sent: the headline, summary and recent jobs come first.
MAX_TEXT_CHARS = 12000

# USD per million tokens (input, output); thinking tokens are billed as output.
# gemini-3.8-flash: Vertex AI introductory price, valid through 2026-12-31
# (cloud.google.com/vertex-ai/generative-ai/pricing); it doubles to 1.50 / 7.50 on 2027-01-01.
PRICES = {"gemini-3.8-flash": (0.75, 3.75)}
# Pre-call guess: output is a short JSON answer; thinking level LOW used no thinking tokens.
ASSUMED_OUTPUT_TOKENS = 120
ASSUMED_THINKING_TOKENS = 50
APP_DIR = Path(__file__).resolve().parents[2]


def load_domains() -> list[dict]:
    with open(APP_DIR / "app" / "data" / "domains.json", encoding="utf-8") as handle:
        return json.load(handle)


def system_prompt(domains: list[dict]) -> str:
    listing = "\n".join(f"- {d['id']}: {d['name']} -- {d['description']}" for d in domains)
    return (
        "You classify resumes by the job FIELD the person works in or is aiming for.\n"
        "Choose exactly one field id from this list:\n"
        f"{listing}\n\n"
        "Rules:\n"
        "- Decide from the headline, the summary and the most recent jobs. Never decide from where the "
        "person studied or from the degree: a Master of Computer Applications student whose experience is "
        "software work is in engineering, not education.\n"
        "- A resume that mixes fields belongs to the field of the main job it is aimed at (the headline, "
        "else the most recent job); put a clear second field, if any, in alt_domain, otherwise \"none\".\n"
        "- A pharmaceutical sales rep is sales, a hospital nurse is healthcare, a teacher is education, "
        "a bookkeeper is finance_accounting, a store cashier is retail_ecommerce, a help-desk or network "
        "technician is engineering.\n"
        "- job_title is the title the resume is aimed at, 2 to 5 words, in plain Title Case; take it from the "
        "headline when there is one.\n"
        "- confidence is high when the field is obvious, medium when two fields are plausible, low when the "
        "resume is too thin to tell.\n"
        "- reason is one short sentence naming the evidence you used.\n"
        "Return only the JSON object."
    )


def response_schema(domains: list[dict]) -> dict:
    ids = [d["id"] for d in domains]
    return {
        "type": "OBJECT",
        "properties": {
            "domain": {"type": "STRING", "enum": ids},
            "alt_domain": {"type": "STRING", "enum": [*ids, "none"]},
            "job_title": {"type": "STRING"},
            "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]},
            "reason": {"type": "STRING"},
        },
        "required": ["domain", "alt_domain", "job_title", "confidence", "reason"],
    }


def price(model: str, prompt_tokens: int, output_tokens: int, thinking_tokens: int) -> float:
    per_in, per_out = PRICES[model]
    return (prompt_tokens * per_in + (output_tokens + thinking_tokens) * per_out) / 1_000_000


def estimate(model: str, prompt: str, text: str) -> float:
    prompt_tokens = (len(prompt) + min(len(text), MAX_TEXT_CHARS)) // 4
    return price(model, prompt_tokens, ASSUMED_OUTPUT_TOKENS, ASSUMED_THINKING_TOKENS)


def sample_pdfs(pdf_dir: Path, per_category: int, seed: int, skip: set[str]) -> list[tuple[str, str, Path]]:
    """(id, category, path) for `per_category` PDFs of every category folder. The shuffle is seeded per
    category, so a larger --per-category extends the sample instead of replacing it."""
    chosen = []
    for folder in sorted(d for d in pdf_dir.iterdir() if d.is_dir()):
        files = sorted(folder.glob("*.pdf"))
        random.Random(f"{seed}-{folder.name}").shuffle(files)
        chosen += [(f"{folder.name}/{f.stem}", folder.name, f) for f in files[:per_category]]
    return [item for item in chosen if item[0] not in skip]


def already_labelled(out_path: Path) -> set[str]:
    if not out_path.exists():
        return set()
    with open(out_path, encoding="utf-8") as handle:
        return {json.loads(line)["id"] for line in handle if line.strip()}


def _with_retry(call, attempts: int = 6, first_wait: float = 10.0):
    """Waits 10, 20, 40... seconds after a 429 or 5xx (neither is billed) so a long run survives them."""
    from google.genai import errors

    for attempt in range(attempts):
        try:
            return call()
        except errors.APIError as error:
            if not (error.code == 429 or error.code >= 500) or attempt == attempts - 1:
                raise
            wait = first_wait * 2**attempt
            print(f"  {error.code} from Vertex AI, retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)


def label_one(client, types, model: str, prompt: str, schema: dict, text: str) -> tuple[dict, tuple[int, int, int]]:
    config = types.GenerateContentConfig(
        system_instruction=prompt,
        temperature=0.0,
        max_output_tokens=1024,
        response_mime_type="application/json",
        response_schema=schema,
        # gemini-3.8-flash rejects MINIMAL; LOW used 0 thinking tokens when measured (MEDIUM used 58).
        thinking_config=types.ThinkingConfig(thinking_level="LOW"),
    )
    response = _with_retry(
        lambda: client.models.generate_content(model=model, contents=text[:MAX_TEXT_CHARS], config=config)
    )
    meta = response.usage_metadata
    tokens = (meta.prompt_token_count or 0, meta.candidates_token_count or 0, meta.thoughts_token_count or 0)
    return json.loads(response.text or "{}"), tokens


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf-dir", type=Path, required=True, help="folder with one sub-folder of PDFs per category")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(PRICES))
    ap.add_argument("--per-category", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, help="only the first N resumes still to label")
    ap.add_argument("--max-usd", type=float, default=1.0,
                    help="hard spending cap for this run; stops before a call that could cross it (default $1)")
    ap.add_argument("--dry-run", action="store_true", help="estimate cost only; no API call")
    args = ap.parse_args()

    sys.path.insert(0, str(APP_DIR))
    from app.services.document_extraction.registry import get_extractor_for_filename

    domains = load_domains()
    prompt, schema = system_prompt(domains), response_schema(domains)
    done = already_labelled(args.out)
    todo = sample_pdfs(args.pdf_dir, args.per_category, args.seed, done)
    todo = todo[: args.limit] if args.limit else todo

    rows = []
    for row_id, category, path in todo:
        try:
            rows.append((row_id, category, get_extractor_for_filename(path.name).extract(path.read_bytes()).text))
        except Exception as error:  # an unreadable PDF is skipped, not labelled
            print(f"  skipping {row_id}: {error}", file=sys.stderr)

    assumed = [estimate(args.model, prompt, text) for _, _, text in rows]
    total = sum(assumed)
    print(f"{len(rows)} resumes to label ({len(done)} already in {args.out.name}), model {args.model}, "
          f"prompt {PROMPT_VERSION}: assumed ${total:.4f} (${total / max(len(rows), 1):.5f} per resume), cap ${args.max_usd:.2f}")
    if args.dry_run:
        return 0

    from google import genai
    from google.genai import types

    from app.config import get_settings

    settings = get_settings()
    if not settings.google_cloud_project:
        print("GOOGLE_CLOUD_PROJECT is not set (ml-service/.env or environment).", file=sys.stderr)
        return 1
    client = genai.Client(vertexai=True, project=settings.google_cloud_project, location=settings.google_cloud_location)

    valid = {d["id"] for d in domains}
    spent, actual = 0.0, [0, 0, 0]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "a", encoding="utf-8") as out:
        for (row_id, category, text), guess in zip(rows, assumed):
            if spent + 2 * guess > args.max_usd:
                print(f"stopping: ${spent:.4f} spent, next call could cross the ${args.max_usd:.2f} cap "
                      f"(re-run to continue; finished resumes are skipped)")
                break
            started = time.monotonic()
            answer, tokens = label_one(client, types, args.model, prompt, schema, text)
            if answer.get("domain") not in valid:
                print(f"  {row_id}: unusable answer {answer}", file=sys.stderr)
                continue
            cost = price(args.model, *tokens)
            spent += cost
            actual = [a + t for a, t in zip(actual, tokens)]
            record = {"id": row_id, "category": category, **answer,
                      "meta": {"model": args.model, "prompt_version": PROMPT_VERSION, "tokens": list(tokens),
                               "text_chars": len(text)}}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(f"  {row_id}: {answer['domain']} ({answer['confidence']}) {answer['job_title']!r}, "
                  f"tokens in/out/think {tokens}, ${cost:.5f} (assumed ${guess:.5f}), {time.monotonic() - started:.1f}s")

    print(f"actual ${spent:.4f} vs assumed ${total:.4f}; tokens in/out/think {tuple(actual)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
