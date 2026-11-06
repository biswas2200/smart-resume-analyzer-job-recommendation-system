"""Labels resumes with Gemini on Vertex AI and turns the answers into common
records (text plus entity positions) for NER training.

Gemini is asked for each entity's exact text, copied from the resume. This
module then finds that text in the resume to get positions, so a paraphrased
or invented value cannot become a training label: it simply is not found,
and the run reports how many were dropped that way.

Read LABELLING.md (next to this file) before a run: model choice, measured
costs, the spending cap and the quality gates.

    cd ml-service
    # 1. estimate the cost first, no API call (cost rule):
    python -m training.data_prep.gemini_label INPUT.jsonl --model gemini-3.5-flash-lite --out OUT.jsonl --dry-run
    # 2. a small real sample, then compare assumed vs actual:
    python -m training.data_prep.gemini_label INPUT.jsonl --model gemini-3.5-flash-lite --out OUT.jsonl --limit 2

INPUT is any JSONL with "id" and "text" fields (a records file from build.py,
or datasets/eval-unseen/sample.jsonl). Authentication is Application Default
Credentials; GOOGLE_CLOUD_PROJECT must be set (in ml-service/.env or the
environment).
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from training.data_prep.dataturks import drop_overlaps, trim
from training.data_prep.schema import Entity, Record, validate_record

# v1: first version. v2 (2026-10-07): rules for the errors measured on the 20
# hand-labelled LiveCareer resumes: references' titles, awards, placeholders and
# duty mentions as job titles; majors, coursework and unfinished certifications
# as degrees; job dates as graduation years; years on their own line missed.
# v3: clients and customers are not employers (seen on DataTurks resumes).
PROMPT_VERSION = "v3"

# The entity types Gemini is asked for: the model's types minus UNKNOWN.
LABELS = {
    "Name": "the candidate's full name",
    "Email Address": "an email address",
    "Phone": "a phone number",
    "Location": "a city, state or country",
    "Designation": "a job title the candidate held or holds, as written in their work history or in a headline/summary describing them, e.g. 'Senior Analyst'",
    "Companies worked at": "the name of an employer the candidate worked for (not a client or customer of that employer)",
    "Degree": "a degree, diploma or certificate the candidate completed, with its field when written next to it, e.g. 'Bachelor of Science : Accounting', 'MBA', 'High School Diploma'",
    "College Name": "the name of a school, college or university",
    "Graduation Year": "the year (or month and year) attached to an education entry, including a year on its own line just above or below a school or degree",
    "Years of Experience": "a stated amount of experience, e.g. '5 years'",
    "Skills": "one skill, tool or technology (one entity per skill, not a whole list)",
}

SYSTEM_PROMPT = (
    "You label resumes for training a named-entity recognition model.\n"
    "Return JSON: {\"entities\": [{\"label\": ..., \"text\": ...}, ...]}, in the order the "
    "entities appear in the resume, every occurrence included.\n"
    "Rules:\n"
    "- \"text\" must be copied character for character from the resume: never correct, "
    "expand, translate or join text from different places.\n"
    "- Use only these labels:\n"
    + "\n".join(f"  - {label}: {meaning}" for label, meaning in LABELS.items())
    + "\n- Placeholders such as 'Company Name', 'City', 'State' or '[Job Title]' are not entities.\n"
    "- Designation is never: the title of a reference or any other person, an award or honour "
    "('Employee of the Year', 'Group Leader'), a word for other people ('employees'), or a role only "
    "mentioned inside a duty description.\n"
    "- Degree is never: a major or coursework on its own, an honour ('Dean's List'), or a certification "
    "still in progress ('Pursuing ...').\n"
    "- Graduation Year is never a date of a job, an award or a certification.\n"
    "- Ignore the References section entirely.\n"
    "- If something does not fit a label, leave it out."
)

# The answer shape, enforced by Gemini itself: "label" can only be one of the
# names above, so a model cannot drift to "Skill" or "Job Title".
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "entities": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"label": {"type": "STRING", "enum": list(LABELS)}, "text": {"type": "STRING"}},
                "required": ["label", "text"],
            },
        }
    },
    "required": ["entities"],
}

# Anonymisation placeholders in the LiveCareer data. Models label them despite
# the prompt, so they are dropped here whatever the model returns.
PLACEHOLDERS = {"company name", "city", "state", "city , state", "city, state", "country", "job title", "[job title]", "n/a", "na", "none"}

# USD per million tokens (input, output); thinking tokens are billed as output.
# Vertex AI list prices for the models this script has been run with; check
# the pricing page before adding a model.
PRICES = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    # Gemini 3.5, global endpoint, standard tier (pricing page, 2026-10-08).
    # More expensive than 2.5, not cheaper: 3.5-flash-lite costs what
    # 2.5-flash costs.
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
}

THINKING_OFF = {"gemini-2.5-flash-lite", "gemini-2.5-flash"}
# Gemini 3.x sets thinking by level, not budget; MINIMAL is the cheapest.
THINKING_LEVEL = {"gemini-3.5-flash-lite": "MINIMAL", "gemini-3.5-flash": "MINIMAL"}

# Pre-call estimate: about 4 characters per token for the prompt; output and
# thinking are rough guesses, replaced by real numbers after the sample run.
ASSUMED_OUTPUT_TOKENS = 1500
# Pro thinking measured at about 5,500-6,900 tokens per resume (2026-10-07).
ASSUMED_THINKING_TOKENS = {"gemini-2.5-pro": 6200, "gemini-3.5-flash-lite": 500, "gemini-3.5-flash": 500}


def price(model: str, prompt_tokens: int, output_tokens: int, thinking_tokens: int) -> float:
    per_in, per_out = PRICES[model]
    return (prompt_tokens * per_in + (output_tokens + thinking_tokens) * per_out) / 1_000_000


def estimate(model: str, text: str) -> tuple[int, int, int, float]:
    prompt = (len(SYSTEM_PROMPT) + len(text)) // 4
    output, thinking = ASSUMED_OUTPUT_TOKENS, ASSUMED_THINKING_TOKENS.get(model, 0)
    return prompt, output, thinking, price(model, prompt, output, thinking)


# Graduation-year rules applied after the model answers. A graduation year
# must belong to an education entry: it has to sit on the line of a degree or
# school, or on the line just above or below it. Measured reasons for doing
# this in code, not only in the prompt: the flash models labelled job date
# ranges ("04/2014 to 02/2016"), years in prose ("joined Accenture in 2006")
# and certification dates, and missed years printed on their own line. Inside
# an education date range ("2016 to 2018") the end date is the graduation year.
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
_DATE = rf"(?:{_MONTH}|\d{{1,2}}/)?(?:19|20)\d{{2}}"
_DATE_RANGE_RE = re.compile(rf"(?P<start>{_DATE})\s*(?:-|–|—|to)\s*(?P<end>{_DATE}|current|present)", re.IGNORECASE)
_YEAR_RE = re.compile(rf"(?<![\w/]){_DATE}(?![\w/])", re.IGNORECASE)
_CERTIFICATION_LINE_RE = re.compile(r"certif|licen[cs]e|expect", re.IGNORECASE)


def _line_bounds(text: str, position: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return start, len(text) if end == -1 else end


def fix_graduation_years(text: str, entities: list[Entity], stats: Counter) -> list[Entity]:
    """Re-derive Graduation Year entities from the education entries the model
    found: keep or add a year only on a degree/school line or the line next to
    it, use the end of an education date range, and skip certification lines."""
    ranges = [m for m in _DATE_RANGE_RE.finditer(text)]
    context: set[tuple[int, int]] = set()
    for anchor in entities:
        if anchor.label not in ("Degree", "College Name"):
            continue
        line = _line_bounds(text, anchor.start)
        context.add(line)
        # The neighbouring lines are the nearest non-empty ones: DataTurks
        # resumes put a blank line between "Calicut University" and "2016 to 2018".
        above = line
        while above[0] > 0:
            above = _line_bounds(text, above[0] - 1)
            if text[above[0]:above[1]].strip():
                context.add(above)
                break
        below = line
        while below[1] < len(text):
            below = _line_bounds(text, below[1] + 1)
            if text[below[0]:below[1]].strip():
                context.add(below)
                break

    def year_span(start: int, end: int) -> tuple[int, int] | None:
        """The graduation-year span a date at [start, end) stands for, or None."""
        line = _line_bounds(text, start)
        if line not in context or _CERTIFICATION_LINE_RE.search(text[line[0]:line[1]]):
            return None
        for match in ranges:
            if start < match.end() and end > match.start():
                if match.group("end").lower() in ("current", "present"):
                    return None
                return match.span("end")
        return start, end

    others = [e for e in entities if e.label != "Graduation Year"]
    model_years = [e for e in entities if e.label == "Graduation Year"]
    spans: set[tuple[int, int]] = set()
    for entity in model_years:
        span = year_span(entity.start, entity.end)
        if span is None:
            stats["graduation_year_dropped"] += 1
        else:
            spans.add(span)
    for line_start, line_end in context:
        for match in _YEAR_RE.finditer(text, line_start, line_end):
            span = year_span(*match.span())
            if span is not None and span not in spans:
                spans.add(span)
                stats["graduation_year_added"] += 1

    # "May 2006" and a bare "2006" inside it can both arrive here; keep the
    # longer one, and never let a year overlap another entity.
    years, _ = drop_overlaps([Entity(start, end, "Graduation Year") for start, end in spans])
    years = [y for y in years if not any(y.start < e.end and y.end > e.start for e in others)]
    return sorted(others + years, key=lambda e: e.start)


def align(text: str, answers: list[dict], stats: Counter) -> list[Entity]:
    """Positions for Gemini's answers. Each answer is searched for from just
    after the previous match (answers come in document order), then anywhere
    in the text; answers with an unknown label or text that is not in the
    resume are dropped and counted."""
    entities, cursor = [], 0
    for answer in answers:
        label, value = answer.get("label"), str(answer.get("text", "")).strip()
        if label not in LABELS or not value:
            stats["bad_label_or_empty"] += 1
            continue
        if value.lower() in PLACEHOLDERS:
            stats["placeholder_dropped"] += 1
            continue
        start = text.find(value, cursor)
        if start == -1:
            start = text.find(value)
        if start == -1:
            stats["not_in_text"] += 1
            continue
        span = trim(text, start, start + len(value))
        entities.append(Entity(span[0], span[1], label))
        cursor = span[1]
    entities, dropped = drop_overlaps(entities)
    stats["overlap_dropped"] += dropped
    entities = fix_graduation_years(text, entities, stats)
    stats["entities_kept"] += len(entities)
    return entities


def _with_retry(call, attempts: int = 6, first_wait: float = 10.0):
    """Run `call`, waiting 10, 20, 40... seconds before trying again after a
    429 RESOURCE_EXHAUSTED (Vertex AI's shared quota pushing back) or a 5xx
    (a passing server fault), so a long unattended run does not stop on one.
    Any other error is raised at once; neither kind is billed."""
    from google.genai import errors

    for attempt in range(attempts):
        try:
            return call()
        except errors.APIError as error:
            if not (error.code == 429 or error.code >= 500) or attempt == attempts - 1:
                raise
            wait = first_wait * 2 ** attempt
            print(f"  {error.code} from Vertex AI, retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)


def label_one(client, types, model: str, text: str) -> tuple[list[dict], tuple[int, int, int]]:
    """One Gemini call. Returns the parsed answers and (prompt, output, thinking) tokens."""
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.0,
        max_output_tokens=16384,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        # The flash models run with thinking off (cheaper, and the task is
        # copying, not reasoning); pro cannot turn thinking off.
        thinking_config=(
            types.ThinkingConfig(thinking_budget=0) if model in THINKING_OFF
            else types.ThinkingConfig(thinking_level=THINKING_LEVEL[model]) if model in THINKING_LEVEL
            else None
        ),
    )
    response = _with_retry(lambda: client.models.generate_content(model=model, contents=text, config=config))
    meta = response.usage_metadata
    tokens = (meta.prompt_token_count or 0, meta.candidates_token_count or 0, meta.thoughts_token_count or 0)
    answers = json.loads(response.text or "{}").get("entities", [])
    return answers, tokens


def already_labelled(out_path: Path) -> set[str]:
    """IDs already in the output file, so a re-run never pays for them twice."""
    if not out_path.exists():
        return set()
    with open(out_path, encoding="utf-8") as handle:
        return {json.loads(line)["id"] for line in handle if line.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", type=Path, help="JSONL with id and text fields")
    ap.add_argument("--model", required=True, choices=sorted(PRICES))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, help="only the first N inputs still to label")
    ap.add_argument("--split", default="train", help="split written on the output records")
    ap.add_argument("--max-usd", type=float, default=1.0,
                    help="hard spending cap for this run; stops before a call that could cross it (default $1)")
    ap.add_argument("--dry-run", action="store_true", help="estimate cost only; no API call")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    done = already_labelled(args.out)
    rows = [row for row in rows if str(row["id"]) not in done]
    rows = rows[: args.limit] if args.limit else rows

    assumed = [estimate(args.model, row["text"]) for row in rows]
    total_assumed = sum(a[3] for a in assumed)
    print(f"{len(rows)} resumes to label ({len(done)} already in {args.out.name}), model {args.model}, "
          f"prompt {PROMPT_VERSION}: assumed ${total_assumed:.4f} (${total_assumed / max(len(rows), 1):.5f} per resume), "
          f"cap ${args.max_usd:.2f}")
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

    stats: Counter = Counter()
    actual = [0, 0, 0]
    spent = 0.0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "a", encoding="utf-8") as out:
        for row, guess in zip(rows, assumed):
            # Budget check before paying: the next call may cost up to twice
            # its estimate (measured overshoot was 1.8x on long resumes).
            if spent + 2 * guess[3] > args.max_usd:
                print(f"stopping: ${spent:.4f} spent, next call could cross the ${args.max_usd:.2f} cap "
                      f"(re-run to continue; finished resumes are skipped)")
                break
            started = time.monotonic()
            answers, tokens = label_one(client, types, args.model, row["text"])
            stats["answers"] += len(answers)
            record = Record(
                id=str(row["id"]), source=f"gemini:{args.model}", split=args.split, text=row["text"],
                entities=align(row["text"], answers, stats),
                meta={"category": row.get("category") or row.get("meta", {}).get("category", ""),
                      "model": args.model, "prompt_version": PROMPT_VERSION},
            )
            problems = validate_record(record)
            if problems:
                print("\n".join(problems), file=sys.stderr)
                return 1
            out.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            out.flush()
            cost = price(args.model, *tokens)
            spent += cost
            actual = [a + t for a, t in zip(actual, tokens)]
            print(f"  {record.id}: {len(record.entities)} entities, tokens in/out/think {tokens}, "
                  f"${cost:.5f} (assumed ${guess[3]:.5f}), {time.monotonic() - started:.1f}s")

    print(f"actual ${spent:.4f} vs assumed ${total_assumed:.4f}; tokens in/out/think {tuple(actual)}")
    print("alignment:", dict(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
