"""Measure what an analysis really costs against what ml-service/
README.md assumes.

Runs the full pipeline (services/pipeline.py) over the
bundled sample resumes -- or the files you pass -- and prints, per call,
the token counts the provider reported and the price they work out to
next to the pre-call estimate (characters / 4). Nothing here is special-
cased: it is the exact code path POST /analyze-file takes.

    python scripts/llm_cost_check.py --dry-run           # estimates only, no API call
    python scripts/llm_cost_check.py                      # real calls (ADC + GOOGLE_CLOUD_PROJECT)
    python scripts/llm_cost_check.py resume.pdf cv.docx   # your own files
    python scripts/llm_cost_check.py --repeat             # run twice: the second pass should be cache hits

Run from ml-service/ with its virtualenv active (the pipeline needs the
local models, and Settings reads ml-service/.env).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services import explainer, parser  # noqa: E402
from app.services.document_extraction.registry import get_extractor_for_filename  # noqa: E402
from app.services.domain_classifier import detect_domain  # noqa: E402
from app.services.llm_client import ledger  # noqa: E402

SAMPLES_DIR = ROOT / "scripts" / "samples"

# The README's per-call assumption, set from the 2026-09-14 measurements
# on the bundled samples (thinking off). The system prompts are measured
# from their actual text below; these are the parts that depend on the
# resume: the narrative's scores/matches block and both answers.
ASSUMED_NARRATE_USER_PROMPT_TOKENS = 170
ASSUMED_OUTPUT_TOKENS = {"extract": 480, "narrate": 150}

CHARS_PER_TOKEN = 4.0


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8")
    return get_extractor_for_filename(path.name).extract(path.read_bytes()).text


def _estimate_tokens(text: str) -> int:
    return round(len(text) / CHARS_PER_TOKEN)


def _pre_call_estimate(resume_text: str, domain_name: str) -> dict[str, dict[str, int]]:
    """What the two prompts will roughly cost before sending anything:
    prompt sizes measured exactly (chars/4), outputs from the README table."""
    settings = get_settings()
    system = parser.SYSTEM_PROMPT + (
        f"\nThe resume belongs to the {domain_name} field: list the skills, "
        "certifications, tools and licences that matter in that field."
    )
    body = parser.compact_resume_text(resume_text, settings.llm_max_input_chars)
    return {
        "extract": {
            "prompt_tokens": _estimate_tokens(system) + _estimate_tokens(body),
            "output_tokens": ASSUMED_OUTPUT_TOKENS["extract"],
        },
        "narrate": {
            "prompt_tokens": _estimate_tokens(explainer.SYSTEM_PROMPT) + ASSUMED_NARRATE_USER_PROMPT_TOKENS,
            "output_tokens": ASSUMED_OUTPUT_TOKENS["narrate"],
        },
    }


def _price(prompt_tokens: int, output_tokens: int, thinking_tokens: int = 0) -> float:
    s = get_settings()
    return (prompt_tokens * s.llm_input_usd_per_1m + (output_tokens + thinking_tokens) * s.llm_output_usd_per_1m) / 1e6


def _print_row(label: str, prompt: int, output: int, thinking: int, cost: float, note: str = "") -> None:
    print(f"  {label:<26} {prompt:>8} {output:>8} {thinking:>9}   ${cost:.6f}  {note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help="resume files (.txt/.pdf/.docx); default: scripts/samples/*")
    ap.add_argument("--dry-run", action="store_true", help="print estimates only; make no API call")
    ap.add_argument("--repeat", action="store_true", help="analyse each file twice to show the cache")
    ap.add_argument("--top-n", type=int, default=3)
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("app.services.llm_client").setLevel(logging.INFO)

    settings = get_settings()
    files = args.files or sorted(SAMPLES_DIR.glob("*.txt"))
    if not files:
        print("no input files", file=sys.stderr)
        return 2

    model = settings.gemini_model if settings.llm_provider == "gemini" else settings.groq_model
    print(f"provider={settings.llm_provider} model={model} thinking_budget={settings.gemini_thinking_budget} "
          f"price=${settings.llm_input_usd_per_1m}/1M in, ${settings.llm_output_usd_per_1m}/1M out "
          f"(thinking billed as output)")
    if settings.llm_provider == "gemini":
        print(f"project={settings.google_cloud_project or '<GOOGLE_CLOUD_PROJECT not set>'} "
              f"location={settings.google_cloud_location}")
    print()

    grand_est = grand_actual = 0.0
    ledger.reset()
    for path in files:
        text = _read_text(path)
        domain = detect_domain(text)
        est = _pre_call_estimate(text, domain.name)
        if domain.engine == "llm":
            est_calls = ["extract", "narrate"]
        else:
            est_calls = ["narrate"]
        est_cost = sum(_price(est[c]["prompt_tokens"], est[c]["output_tokens"]) for c in est_calls)
        grand_est += est_cost

        print(f"== {path.name}: {len(text)} chars, domain={domain.domain} ({domain.engine}), "
              f"confidence={domain.confidence}")
        print(f"  {'call':<26} {'prompt':>8} {'output':>8} {'thinking':>9}   {'est. USD':<10}")
        for call in est_calls:
            _print_row(f"assumed {call}", est[call]["prompt_tokens"], est[call]["output_tokens"], 0,
                       _price(est[call]["prompt_tokens"], est[call]["output_tokens"]))
        print(f"  {'assumed total':<26} {'':>8} {'':>8} {'':>9}   ${est_cost:.6f}")

        if args.dry_run:
            print()
            continue

        # Imported here so --dry-run never loads the pipeline's heavier deps.
        from app.services import pipeline

        passes = 2 if args.repeat else 1
        for n in range(passes):
            started = time.perf_counter()
            response = pipeline.analyze_text(text, top_n=args.top_n)
            elapsed = time.perf_counter() - started
            usage = response.llm_usage
            if usage is None:
                print(f"  pass {n + 1}: no LLM call was made ({elapsed:.1f}s, "
                      f"locked={response.recommendations_locked}, reason={response.lock_reason})")
                continue
            for call in usage.details:
                _print_row(f"actual {call.purpose}" + (" (cache)" if call.cache_hit else ""),
                           call.prompt_tokens, call.output_tokens, call.thinking_tokens,
                           call.estimated_cost_usd)
            print(f"  {'actual total':<26} {'':>8} {'':>8} {'':>9}   ${usage.estimated_cost_usd:.6f}  "
                  f"({elapsed:.1f}s, explanation_source={response.explanation_source}, "
                  f"{len(response.matches)} matches, {len(response.profile.skills)} skills, "
                  f"ai_extraction_used={response.ai_extraction_used})")
            if n == 0:
                grand_actual += usage.estimated_cost_usd
                ratio = usage.estimated_cost_usd / est_cost if est_cost else float("nan")
                print(f"  actual / assumed = {ratio:.2f}x")
        print()

    print(f"assumed total for {len(files)} file(s): ${grand_est:.6f}")
    if not args.dry_run:
        print(f"actual total (first pass):         ${grand_actual:.6f}   "
              f"ledger: {ledger.calls} calls, {ledger.cache_hits} cache hits, "
              f"{ledger.prompt_tokens} in / {ledger.output_tokens} out / {ledger.thinking_tokens} thinking")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
