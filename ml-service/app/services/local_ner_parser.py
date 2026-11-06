"""Local, zero-external-API resume parsing. Runs a resume-specialized NER
model (by default our fine-tune of yashpwr/resume-ner-bert, loaded from
models/ner/teacher-run1; see Settings.ner_model_name) fully offline -- no API key, no outbound
network call per request, no per-request cost. This is the default parsing
backend (see Settings.parser_backend in app/config.py); parser.py falls back
to the LLM-based path only when explicitly configured to.

The model tags flat entity spans (one BIO-tagged label per token) with no
signal about which spans belong to the same job/degree, and no entity type
at all for a job's date range or free-text description. This module's job is
turning that flat, incomplete signal into a best-effort ResumeProfile -- the
assembly logic below documents each heuristic and its known limitations
inline, since the tradeoffs are the interesting/non-obvious part of this
file.
"""

import hashlib
import json
import logging
import re
import shutil
import time
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.config import SERVICE_DIR, get_settings
from app.models.schemas import EducationEntry, ExperienceEntry, ResumeProfile
from app.services.dictionary_skills import find_skills
from app.services.normalizer import normalize_skills
from app.services.sectioner import split_sections

# One row of transformers.pipeline("token-classification", ...) output with
# aggregation_strategy="simple": {"entity_group": str, "word": str,
# "score": float, "start": int, "end": int}. Kept as a plain dict (not a
# TypedDict/dataclass) since we only ever read two of its keys here.
NerEntity = dict

logger = logging.getLogger(__name__)

# "Degree"/"Designation" are anchors: each occurrence signals a new
# education/experience record is starting (matches the common one-line/
# one-bullet-per-degree-or-job resume convention). The other groups below
# are attributes that fill in whichever anchor record is currently open --
# they never start a new record on their own.
_EDUCATION_FILLER_FIELDS = {"College Name": "institution", "Graduation Year": "year"}
_EXPERIENCE_FILLER_FIELDS = {"Companies worked at": "organization"}

# Splits a single "Skills" entity span (which often tags a whole
# comma/slash-separated list as one span, e.g. "Python, SQL, Java") into
# individual skill strings before they're handed to normalize_skills().
_SKILL_DELIMITER_RE = re.compile(r"[,/|;•\n]+|\band\b", re.IGNORECASE)

# Deliberately simple, not exhaustive -- these two exist as a more reliable
# alternative to the model's own Email Address/Phone tags for the common
# case; the NER tags are still used as a fallback (see _entities_to_profile)
# for formatting the regexes miss.
#
# _EMAIL_RE's local part and domain are each exactly one unbounded character
# class, never two adjacent/nested ones -- this runs on user-uploaded resume
# text, so avoiding any backtracking-blowup shape matters more than
# rejecting a domain with no dot in it (an edge case this lenient,
# heuristic check doesn't need to catch anyway).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+")
#
# _PHONE_RE's first branch is the Indian mobile written as two groups of
# five ("+91 98765 43210"), which the 3/4-digit grouping of the second
# branch can't split; it requires the separator, so a bare ten-digit run
# still goes to the second branch.
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\d{5}[-.\s]\d{5}|\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})"
)

# Matches date ranges like "Jan 2020 - Mar 2022", "2019-2021",
# "Jun 2021 to Present". There is no NER entity for a job's duration at all,
# so this is the only signal available for ExperienceEntry.duration.
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
_DATE_TOKEN = rf"(?:{_MONTH})?\d{{4}}"
_DATE_END_TOKEN = rf"(?:(?:{_MONTH})?\d{{4}}|[Pp]resent|[Cc]urrent)"
_DATE_RANGE_RE = re.compile(rf"{_DATE_TOKEN}\s*(?:-|–|—|to)\s*{_DATE_END_TOKEN}")

# A date match more than this many characters away from a job's title
# position is considered unrelated rather than guessed at -- better to leave
# duration blank than to attach a clearly-wrong nearby date.
_MAX_DATE_MATCH_DISTANCE_CHARS = 300

# A standalone 4-digit year, e.g. the "2017" in "...engineering\n\nAugust
# 2013 to June 2017" or a bare "2016" on its own line. The NER model is
# weak at "Graduation Year" on real resumes (21% token F1 across the 220
# ground-truth resumes in ml-service/scripts/evaluate_ner_extraction.py), so
# this fallback is the main signal for the field, not a refinement.
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# Entities the model is less confident about than this are dropped before
# assembly. Measured, 0.0 (keep everything) is best: on half of the 220
# annotated resumes, macro F1 over the profile fields was 70% at 0.0, 66%
# at 0.4 and 39% at 0.6 -- once entities are aggregated per word ("first",
# see _get_ner_pipeline) the low-confidence tail is mostly real, partially
# tagged titles/companies, not noise. Kept as a knob for a future model.
_MIN_ENTITY_SCORE = 0.0

# An education-section line naming an institution. Word-bounded so e.g.
# "schooling" doesn't count; the short acronyms cover the Indian institute
# names common in the annotated data (IIT Bombay, NIT Trichy, ...).
_INSTITUTION_KEYWORD_RE = re.compile(
    r"\b(?:universit(?:y|ies)|colleges?|institutes?|institutions?|schools?|academy|vidyalaya|vishwavidyalaya|mahavidyalaya"
    r"|polytechnic|faculty|iit|nit|iiit|iisc|iim|bits)\b",
    re.IGNORECASE,
)
# Separators between the degree, institution and place on one line. The
# dashes include the en/em dash and the full-width "－" that some resume
# builders (e.g. LiveCareer exports) put between institution and city.
_INSTITUTION_SEPARATOR_RE = re.compile(r"\s+[-–—－|]\s+|\s+:\s+|,|\t")

# _extract_name: how far down to look, what a name line looks like (2-4
# words of letters -- any script, so "José García" counts -- plus dots,
# apostrophes and hyphens), and words that mark a heading or a job title
# rather than a person. `[^\W\d_]` is "a letter" in Python's re.
_NAME_SEARCH_LINES = 3
_NAME_WORD = r"[^\W\d_](?:[^\W\d_]|[.'-])*"
_NAME_LINE_RE = re.compile(rf"{_NAME_WORD}(?: {_NAME_WORD}){{1,5}}")
_NOT_NAME_WORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "biodata", "summary", "objective", "contact",
    "experience", "education", "skills", "details", "personal",
    "engineer", "developer", "manager", "analyst", "consultant", "designer", "associate", "intern",
    "specialist", "executive", "officer", "lead", "architect", "administrator", "scientist", "director",
}


def parse_resume_local(
    resume_text: str, ner_pipeline: Callable[[str], list[NerEntity]] | None = None, ner_skills: bool = True
) -> ResumeProfile:
    """Parse resume_text into a ResumeProfile using the local NER model. Runs
    the model per-chunk (see _chunk_text) since it has a 512-token limit, and
    merges every chunk's entities before assembling the profile. Pass
    ner_pipeline to inject a fake in tests -- the real model is only built
    (and only then does it need to be installed/downloaded) if this is left
    as None.

    FR-1.6/1.7: the NER model only ever sees the Experience and Education
    sections (split_sections), which is both cheaper and more accurate than
    running it over the whole document -- skills are instead found by
    deterministic dictionary matching over the *whole* text
    (dictionary_skills.find_skills) and merged with whatever "Skills" entity
    spans the NER pass happens to also produce, for recall. A resume with no
    heading this sectioner recognizes falls back to feeding the NER model
    the whole text, unchanged from the pre-step-2 pipeline.
    """
    resume_text = fix_mojibake(resume_text)
    pipeline_fn = ner_pipeline or _get_ner_pipeline()
    sections = split_sections(resume_text)
    ner_text = (
        f"{sections.experience}\n{sections.education}".strip()
        if (sections.experience or sections.education)
        else resume_text
    )

    entities: list[NerEntity] = []
    for chunk in _chunk_text(ner_text):
        entities.extend(_with_source_text(pipeline_fn(chunk), chunk))

    profile = _entities_to_profile(entities, resume_text)
    if not ner_skills:
        # The model was trained on IT resumes: outside that field its "Skills" spans are
        # ordinary phrases ("important to sales process", "into GI"), so only the
        # dictionary and the resume's own Skills section are trusted there.
        profile.skills = []
    profile.skills = normalize_skills(
        [*find_skills(resume_text), *profile.skills, *_skills_from_section(sections.skills)]
    )
    assembled = _assemble_education(profile.education, sections.education)
    if assembled is not None:
        profile.education = assembled
    else:
        # No degree written on any line: keep the entity-order records and
        # repair them as well as the lines allow.
        profile.education = _fill_education_years(profile.education, sections.education)
        profile.education = _fill_education_institutions(profile.education, sections.education)
        profile.education = _align_education_to_lines(profile.education, sections.education)
        profile.education = _widen_education_institutions(profile.education, sections.education)
        profile.education = _repair_degrees(profile.education, sections.education)
    # Without an Experience heading the whole text is searched, but only to
    # repair jobs the model found; adding jobs from free text would be a guess.
    profile.experience = _repair_experience(
        profile.experience, sections.experience or resume_text, allow_new_records=bool(sections.experience)
    )
    profile.experience = _fill_missing_durations(profile.experience, resume_text)
    return profile


@lru_cache(maxsize=1)
def _get_ner_pipeline() -> Callable[[str], list[NerEntity]]:
    """Lazily build and cache the real transformers NER pipeline. Imported
    inside the function (not at module load time) so that importing this
    module -- and injecting a fake pipeline in tests -- never requires
    `transformers` to actually download the model.
    """
    from transformers import pipeline

    settings = get_settings()
    # "first" aggregates per *word* (each word takes the label of its first
    # subword token). "simple" aggregated per subword token, so a word whose
    # subwords got different labels was split into fragments like "##ance"
    # that then became their own degree/company records.
    # revision= loads exactly the commit engine_fingerprint() hashes
    # (fingerprint.py); without it the fingerprint named a pinned revision
    # while the pipeline silently loaded whatever was on "main". A local
    # directory has no commits, so its pin is the weights' SHA-256 instead.
    local_dir = resolve_local_model_dir(settings.ner_model_name)
    if local_dir is not None:
        verify_local_model(local_dir, settings.ner_model_revision)
        logger.info("Loading NER model from %s (sha256 %s)", local_dir, settings.ner_model_revision[:12])
        return pipeline("token-classification", model=str(local_dir), aggregation_strategy="first")
    logger.info("Loading NER model %s@%s", settings.ner_model_name, settings.ner_model_revision[:12])
    return pipeline(
        "token-classification",
        model=settings.ner_model_name,
        revision=settings.ner_model_revision,
        aggregation_strategy="first",
    )


def resolve_local_model_dir(name: str) -> Path | None:
    """The directory `name` refers to, if it is a saved model on disk (a
    relative path is taken from ml-service/), else None for a hub id. A name
    that looks like a path but does not exist raises, so a missing download
    fails at start-up instead of silently querying the hub for "models/...".
    """
    path = _local_model_path(name)
    if path is not None and path.is_dir():
        return path
    if path is not None and name.startswith(("models/", "./", "/")):
        raise FileNotFoundError(
            f"NER model directory {path} not found. Set NER_MODEL_GCS_URI to download it at "
            "start-up, or run scripts/fetch_ner_models.sh first."
        )
    return None


def ensure_local_model(settings) -> None:
    """At start-up: when the NER model is a local folder that is missing and
    NER_MODEL_GCS_URI names its copy in the bucket, download it with ADC.
    The files land in a staging folder, are checked against the pinned
    SHA-256, and only then take the model folder's place, so a failed or
    tampered download never becomes the model. Does nothing for a hub id,
    an existing folder, or the LLM parser.
    """
    if settings.parser_backend != "local" or not settings.ner_model_gcs_uri:
        return
    path = _local_model_path(settings.ner_model_name)
    if path is None or path.is_dir():
        return

    from app.services.gcs_download import download_folder

    staging = path.parent / f".{path.name}.download"
    logger.info("NER model %s missing; downloading %s", path, settings.ner_model_gcs_uri)
    start = time.perf_counter()
    try:
        count = download_folder(settings.ner_model_gcs_uri, staging)
        verify_local_model(staging, settings.ner_model_revision)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    staging.rename(path)
    logger.info("Downloaded the NER model (%d files) in %.0fs", count, time.perf_counter() - start)


def _local_model_path(name: str) -> Path | None:
    """Where `name` would live on disk (relative paths are taken from
    ml-service/), or None when it reads as a Hugging Face id."""
    path = Path(name)
    if path.is_absolute():
        return path
    path = SERVICE_DIR / path
    if path.is_dir() or name.startswith(("models/", "./")):
        return path
    return None


def verify_local_model(model_dir: Path, expected_sha256: str) -> None:
    """Refuse weights other than the pinned ones: the engine fingerprint
    names the pin, so loading anything else would make it lie."""
    digest = hashlib.sha256()
    with open(model_dir / "model.safetensors", "rb") as weights:
        for block in iter(lambda: weights.read(1 << 20), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise ValueError(
            f"{model_dir}/model.safetensors has SHA-256 {actual}, but NER_MODEL_REVISION pins {expected_sha256}."
        )


def _with_source_text(entities: list[NerEntity], chunk: str) -> list[NerEntity]:
    """Each entity's text as it is written in the resume. The pipeline's
    "word" is rebuilt from subword tokens, which puts spaces around
    punctuation ("Technical Lead / Operations Manager" for
    "Technical Lead/Operations Manager"), so the same title would not match
    itself. The entity's character offsets into the chunk give the original
    text; runs of whitespace inside it (a span across a line break) become
    one space. Entities without usable offsets keep their "word".
    """
    fixed = []
    for entity in entities:
        start, end = entity.get("start"), entity.get("end")
        if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chunk):
            entity = {**entity, "word": " ".join(chunk[start:end].split())}
        fixed.append(entity)
    return fixed


# Each whitespace-delimited word *with* the whitespace that follows it, so a
# chunk can be rebuilt with the original newlines intact.
_WORD_WITH_TRAILING_SPACE_RE = re.compile(r"\S+\s*")


def _chunk_text(text: str, max_words: int = 380, overlap_words: int = 50) -> list[str]:
    """Split text into overlapping word-count windows so each chunk stays
    safely under the model's 512-subword-token limit. Word count (not a real
    tokenizer call) is a conservative proxy -- English text averages under
    1.3 BERT subword tokens per word, so 380 words leaves real margin. The
    overlap means a section straddling a hard chunk boundary very likely
    appears whole in at least one of the two overlapping chunks; the
    resulting duplicate entities near the boundary are handled by
    _dedupe_records() rather than by reconciling chunk offsets, since nothing
    downstream needs the entities' position in the *original* document.

    Chunks keep the original whitespace, including newlines: line breaks are
    one of the strongest signals in a resume (a title or company is usually
    on a line of its own), and joining words with single spaces used to
    flatten every long resume into one line before the model saw it.
    """
    words = _WORD_WITH_TRAILING_SPACE_RE.findall(text)
    if len(words) <= max_words:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append("".join(words[start:end]).rstrip())
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def _apply_education_entity(group: str, text: str, current_edu: dict | None, education: list[dict]) -> dict | None:
    """Handles one "Degree" (anchor) or education-filler entity, returning
    what should become the new current_edu. A filler with no anchor open
    yet (e.g. a stray "College Name" before any "Degree") is dropped rather
    than starting a placeholder record -- an empty-degree row would just be
    noise, most likely from a model misfire (the model is ~49% token F1 on real
    resumes, far from perfect).
    """
    if group == "Degree":
        if current_edu is not None:
            education.append(current_edu)
        return {"degree": text, "institution": "", "year": ""}
    field = _EDUCATION_FILLER_FIELDS[group]
    if current_edu is not None and current_edu[field].strip().lower() == text.lower():
        return current_edu  # the same value again (overlapping chunks)
    if current_edu is not None and field == "institution" and current_edu["institution"]:
        # A second institution while the open record already has one: the model
        # missed the next record's degree. Overwriting would silently lose the
        # first institution, so close the record and open one without a degree
        # (the line-based passes below fill the degree back in).
        education.append(current_edu)
        return {"degree": "", "institution": text, "year": ""}
    if current_edu is not None:
        current_edu[field] = text
    return current_edu


def _apply_experience_entity(group: str, text: str, current_exp: dict | None, experience: list[dict]) -> dict | None:
    """Handles one "Designation" (anchor) or experience-filler entity,
    returning what should become the new current_exp. Same drop-if-no-anchor
    behavior as _apply_education_entity, for the same reason.
    """
    if group == "Designation":
        if current_exp is not None:
            experience.append(current_exp)
        return {"title": text, "organization": "", "duration": "", "description": ""}
    field = _EXPERIENCE_FILLER_FIELDS[group]
    if current_exp is not None and current_exp[field].strip().lower() == text.lower():
        return current_exp  # the same company again (overlapping chunks)
    if current_exp is not None and current_exp[field]:
        # A second company while the open job already has one: the model
        # missed this job's title. Overwriting lost the first company and the
        # whole second job; start a title-less record instead and let
        # _repair_experience read the title off the resume line.
        experience.append(current_exp)
        return {"title": "", "organization": text, "duration": "", "description": ""}
    if current_exp is not None:
        current_exp[field] = text
        return current_exp
    # A company before any title (the model missed this job's title): keep it
    # as a title-less record. _repair_experience reads the title off the line
    # and drops the record when there is none, which is what dropping the
    # company here used to do for stray mentions.
    return {"title": "", "organization": text, "duration": "", "description": ""}


def _entities_to_profile(
    entities: list[NerEntity], full_text: str, min_score: float = _MIN_ENTITY_SCORE
) -> ResumeProfile:
    """Assemble a ResumeProfile from a flat, already-in-document-order list
    of NER entities. Pure function (no model, no I/O) so tests can exercise
    every grouping/edge case with hand-built entity lists. Entities the
    model is less than min_score confident about are dropped first.
    """
    education: list[dict] = []
    experience: list[dict] = []
    current_edu: dict | None = None
    current_exp: dict | None = None
    education_groups = {"Degree", *_EDUCATION_FILLER_FIELDS}
    experience_groups = {"Designation", *_EXPERIENCE_FILLER_FIELDS}
    simple_spans = {"Skills": [], "Email Address": [], "Phone": [], "Name": []}

    for entity in entities:
        group = entity.get("entity_group", "")
        text = str(entity.get("word", "")).strip()
        if not text or float(entity.get("score", 1.0)) < min_score:
            continue

        if group in education_groups:
            current_edu = _apply_education_entity(group, text, current_edu, education)
        elif group in experience_groups:
            current_exp = _apply_experience_entity(group, text, current_exp, experience)
        elif group in simple_spans:
            simple_spans[group].append(text)
        # "Years of Experience", "Location", "UNKNOWN" (and anything else
        # the model emits) are intentionally not mapped to any
        # ResumeProfile field -- a known local-path gap, not a bug.

    skill_spans = simple_spans["Skills"]
    email_spans = simple_spans["Email Address"]
    phone_spans = simple_spans["Phone"]
    name_spans = simple_spans["Name"]

    if current_edu is not None:
        education.append(current_edu)
    if current_exp is not None:
        experience.append(current_exp)

    education = _dedupe_records(education, ("degree", "institution"))
    experience = _dedupe_records(experience, ("title", "organization"))
    experience = _fill_experience_durations(experience, full_text)
    # experience[*]["description"] is intentionally left "" -- there is no
    # NER entity for free-text description, and unlike duration, no regex is
    # safe/general enough across resume layouts (bullets, tables,
    # multi-column PDF-as-text) to guess at it without risking pulling in
    # unrelated content (e.g. the next job's title). Users who need this
    # field can opt into the LLM parsing backend instead.

    return ResumeProfile(
        name=_extract_name(full_text) or (name_spans[0] if name_spans else ""),
        email=_extract_email(full_text) or (email_spans[0] if email_spans else ""),
        phone=_extract_phone(full_text) or (phone_spans[0] if phone_spans else ""),
        skills=normalize_skills(_split_skill_spans(skill_spans)),
        experience=[ExperienceEntry(**entry) for entry in experience],
        education=[EducationEntry(**entry) for entry in education],
    )


def _dedupe_records(records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """Drop later records whose key_fields match one already seen (case-
    insensitive), preserving first-seen order. Needed because overlapping
    chunks (see _chunk_text) can cause the same real job/degree to be
    emitted twice by the NER pass.
    """
    seen: set[tuple[str, ...]] = set()
    deduped = []
    for record in records:
        key = tuple(record[field].strip().lower() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _nearest_unconsumed_match_index(matches: list[re.Match], consumed: list[bool], title_pos: int) -> int | None:
    """Index of the not-yet-consumed match in matches closest to title_pos,
    or None if every match is either already consumed or farther away than
    _MAX_DATE_MATCH_DISTANCE_CHARS.
    """
    best_index = None
    best_distance = None
    for index, match in enumerate(matches):
        if consumed[index]:
            continue
        distance = abs(match.start() - title_pos)
        if distance > _MAX_DATE_MATCH_DISTANCE_CHARS:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def _own_line_match_index(matches: list[re.Match], consumed: list[bool], text: str, pos: int) -> int | None:
    """The unused date range written on the job's own line or on the next two
    lines ("Software Engineer | Acme | Jun 2024 - Dec 2024", or the dates on the
    line under the title). Closer by characters is not closer on the page: the
    previous section's last date can be nearer than this job's own dates."""
    start = text.rfind("\n", 0, pos) + 1
    end = start
    for _ in range(3):
        nxt = text.find("\n", end)
        if nxt == -1:
            end = len(text)
            break
        end = nxt + 1
    end = max(end - 1, start)
    for index, match in enumerate(matches):
        if not consumed[index] and start <= match.start() < end:
            return index
    return None


def _fill_experience_durations(experience: list[dict], full_text: str) -> list[dict]:
    """Best-effort fill of each experience entry's duration by matching it
    to the nearest not-yet-used date-range match in the surrounding text.
    Heuristic, not exact: proximity-based matching can misattribute a date
    when the same job title appears more than once in the resume, or when a
    job's date range is written far from its title. Leaves duration "" when
    no match is close enough (see _MAX_DATE_MATCH_DISTANCE_CHARS) rather
    than guessing.
    """
    matches = list(_DATE_RANGE_RE.finditer(full_text))
    consumed = [False] * len(matches)

    for entry in experience:
        title_pos = full_text.find(entry["title"]) if entry["title"] else -1
        if title_pos == -1:
            continue

        best_index = _own_line_match_index(matches, consumed, full_text, title_pos)
        if best_index is None:
            best_index = _nearest_unconsumed_match_index(matches, consumed, title_pos)
        if best_index is not None:
            consumed[best_index] = True
            entry["duration"] = matches[best_index].group(0)

    return experience


def _fill_education_years(education: list[EducationEntry], education_section_text: str) -> list[EducationEntry]:
    """Best-effort fill of each still-empty EducationEntry.year from
    standalone 4-digit years found in the isolated Education section text
    (see sectioner.py), assigned positionally -- the i-th unconsumed year in
    that text fills the i-th entry still missing a year -- rather than by
    matching each entry's degree/institution text back into the original
    resume the way _fill_experience_durations does for job titles. That
    approach doesn't transfer here: an entity's reconstructed text (e.g.
    "b college of engineering and technology" for what was actually
    "B.v.b college...") is built from subword tokens and routinely doesn't
    `.find()` back into the original text at all, so proximity-to-anchor
    isn't a reliable signal for this field the way it is for a job title.
    Scoped to the Education section alone (not the whole resume) so a job's
    own date range is never mistaken for a graduation year.
    """
    if not education_section_text:
        return education

    years = iter(_YEAR_RE.findall(education_section_text))
    for entry in education:
        if entry.year:
            continue
        year = next(years, None)
        if year is None:
            break
        entry.year = year

    return education


def _institution_in_line(line: str) -> str:
    """The part of one education-section line that names an institution, or
    "" if it doesn't look like one. A line like "B.E, Anna University,
    Chennai" is split on its separators and only the piece carrying the
    keyword is kept, so the degree isn't repeated in the institution field.
    """
    for piece in _INSTITUTION_SEPARATOR_RE.split(line):
        piece = piece.strip(" .")
        if _INSTITUTION_KEYWORD_RE.search(piece):
            return piece
    return ""


def _fill_education_institutions(
    education: list[EducationEntry], education_section_text: str
) -> list[EducationEntry]:
    """Best-effort fill of each still-empty EducationEntry.institution from
    lines of the Education section that name an institution (a keyword such
    as "University", "College" or "Institute"), assigned positionally like
    _fill_education_years. The NER model misses many institutions on real
    resumes (52% token F1 on "College Name"), and on the DataTurks held-out half this fallback lifts institution
    F1 from 49% to 63%.

    When the model folded the institution into the degree span (e.g. degree
    "Bachelor of Engg in IT Shivaji University Kolhapur"), the institution
    is trimmed off the end of the degree once it has its own field.
    """
    if not education_section_text:
        return education

    institutions = iter(
        found for line in education_section_text.splitlines() if (found := _institution_in_line(line))
    )
    for entry in education:
        if entry.institution:
            continue
        institution = next(institutions, None)
        if institution is None:
            break
        entry.institution = institution
        if entry.degree.lower().endswith(institution.lower()) and len(entry.degree) > len(institution):
            entry.degree = entry.degree[: -len(institution)].strip(" ,-|")

    return education


def _align_education_to_lines(
    education: list[EducationEntry], education_section_text: str
) -> list[EducationEntry]:
    """Pairs each degree with the institution and year written next to it.

    The model's entities come in document order, and assembly attaches an
    institution to the degree before it. That is right when a resume writes
    the degree first, but on one that writes the institution line first
    ("Nitte Meenakshi Institute of Technology / Master of Computer
    Applications (MCA); SGPA: 7.69 2025 - 2027 / Koshys Group of
    Institutions / Bachelor of Computer Applications (BCA)") every degree
    got the next degree's institution. Here the order is read from the
    lines: if the first institution line comes before the first degree
    line, each degree takes the institution line just above it, otherwise
    the one just below. An institution on the degree's own line wins, and
    an entry is left alone when no institution line is next to it.

    The year is the latest year on the degree's line (or else on its
    institution's line), so "2025 - 2027" gives 2027. A degree's trailing
    separator (the ";" before "SGPA") is dropped.
    """
    for entry in education:
        entry.degree = entry.degree.strip().rstrip(" ;,:|-–").strip()
    if not education_section_text:
        return education

    lines = [line.strip() for line in education_section_text.splitlines() if line.strip()]
    degree_lines: dict[int, int] = {}
    for index, entry in enumerate(education):
        if entry.degree:
            found = next((i for i, line in enumerate(lines) if entry.degree.lower() in line.lower()), None)
            if found is not None:
                degree_lines[index] = found
    if not degree_lines:
        return education

    taken = set(degree_lines.values())
    institution_lines = {i for i, line in enumerate(lines) if i not in taken and _institution_in_line(line)}
    institution_first = bool(institution_lines) and min(institution_lines) < min(taken)
    step = -1 if institution_first else 1

    for index, line_no in degree_lines.items():
        entry = education[index]
        same_line = _institution_in_line(lines[line_no])
        paired = line_no + step
        if same_line and entry.degree.lower() not in same_line.lower():
            entry.institution = same_line
        elif paired in institution_lines:
            entry.institution = _institution_in_line(lines[paired])
        years = _YEAR_RE.findall(lines[line_no]) or (_YEAR_RE.findall(lines[paired]) if paired in institution_lines else [])
        if years:
            entry.year = max(years)
    return education


def _widen_education_institutions(
    education: list[EducationEntry], education_section_text: str
) -> list[EducationEntry]:
    """Restores the start of an institution name the model cut short. On
    "B.Tech, Savitribai Phule Pune University, 2022" the model tags
    "Savitribai Phule" and "University" as separate pieces and drops "Pune",
    so the entry kept only the tail. When one separator-delimited piece of an
    Education line names an institution, ends with the entry's institution
    and is longer, the whole piece is used instead -- unless it also holds
    the entry's degree, so a degree and institution written without a
    separator are not merged.
    """
    if not education_section_text:
        return education

    pieces = [
        piece
        for line in education_section_text.splitlines()
        for raw in _INSTITUTION_SEPARATOR_RE.split(line)
        if _INSTITUTION_KEYWORD_RE.search(piece := raw.strip(" ."))
    ]
    for entry in education:
        short = entry.institution.strip(" .").lower()
        if not short:
            continue
        for piece in pieces:
            lowered = piece.lower()
            if (
                len(lowered) > len(short)
                and lowered.endswith(short)
                and lowered[-len(short) - 1] == " "
                and not (entry.degree and entry.degree.lower() in lowered)
            ):
                entry.institution = piece
                break
    return education


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w()]+", " ", text.lower()).split())


def _assemble_education(
    education: list[EducationEntry], education_section_text: str
) -> list[EducationEntry] | None:
    """Builds the education records from the Education section's own lines.

    Each line that holds a degree (a degree the model found, or one written
    like B.Tech / MCA / Bachelor of ... / 12th) owns a block of lines: from
    that line to the next degree's block. Resumes write either "degree, then
    institution" or "institution, then degree"; the order is read once from
    the first institution line, and a block then starts at the institution
    line just above its degree (or at the degree line itself). Inside its
    block each degree takes the first institution named there and the latest
    year written there ("Aug 2022 - Jun 2025" gives 2025). So a degree can
    never take a neighbour's institution or year, which the entity-order
    pairing did on every layout that is not "degree, institution" per line.

    Returns None when the section holds no degree line, so the caller keeps
    the entity-order records.
    """
    lines = _clean_lines(education_section_text)
    if not lines:
        return None

    entries = [(e, _norm(_strip_grade(e.degree))) for e in education if e.degree.strip()]
    used_entries: set[int] = set()
    degree_at: dict[int, tuple[str, EducationEntry | None]] = {}
    for index, line in enumerate(lines):
        pieces = _degree_pieces(line)
        norm_line = _norm(line)
        entity = next(
            (
                (i, e)
                for i, (e, key) in enumerate(entries)
                if i not in used_entries and key and key in norm_line
            ),
            None,
        )
        if entity is None and not pieces:
            continue
        if not pieces and _institution_in_line(line):
            # The model tagged part of an institution name as a degree
            # ("MES MSPS" in "MES MSPS First Grade College, ..."): the line
            # names an institution and writes no degree, so it is not one.
            if entity is not None:
                used_entries.add(entity[0])
            continue
        text = ""
        if entity is not None:
            used_entries.add(entity[0])
            text = _strip_grade(entries[entity[0]][0].degree)
        if pieces:
            piece = _strip_grade(pieces[0])
            if not text or (_norm(text) in _norm(piece) and len(piece) > len(text)):
                text = piece
        text = _balance_parenthesis(text, line) if text else text
        if text and len(text.split()) <= 14:
            degree_at[index] = (text, entity[1] if entity else None)
    if not degree_at:
        return None

    degree_lines = sorted(degree_at)
    institution_lines = [i for i, line in enumerate(lines) if i not in degree_at and _institution_in_line(line)]
    institution_first = bool(institution_lines) and institution_lines[0] < degree_lines[0]

    starts = []
    for d in degree_lines:
        start = d
        if institution_first:
            above = [i for i in institution_lines if i < d and (not starts or i > starts[-1])]
            if above:
                start = above[-1]
        starts.append(start)

    records = []
    for k, d in enumerate(degree_lines):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        block = lines[starts[k] : end]
        text, entity = degree_at[d]
        institution = _institution_in_line_excluding(lines[d], text)
        if not institution:
            institution = next((found for line in block if (found := _institution_in_line_excluding(line, text))), "")
        if not institution and entity is not None and entity.institution:
            institution = entity.institution
        institution = _trim_trailing_place(institution, [e.institution for e in education])
        text = _drop_institution_from_degree(text, institution)
        years = [y for line in block for y in _YEAR_RE.findall(line)]
        year = max(years) if years else (entity.year if entity is not None and entity.year else "")
        records.append(EducationEntry(degree=text, institution=institution, year=year))

    # Records the model found whose degree is not on any line (its text is
    # rebuilt from subwords): keep them rather than lose them.
    produced = [_norm(r.degree) for r in records]
    for i, (entry, key) in enumerate(entries):
        if i in used_entries or not key:
            continue
        if any(key in p or p in key for p in produced):
            continue
        if any(key in _norm(line) for line in lines):
            continue  # written on a line that holds no degree: a misfire, not a degree
        records.append(EducationEntry(degree=_strip_grade(entry.degree), institution=entry.institution, year=entry.year))
    return records


def _trim_trailing_place(institution: str, model_spans: list[str]) -> str:
    """Drops a city written straight after an institution ("... Institute of
    Technology Bengaluru") when the model's own span ends where the name does.
    Only a one- or two-word remainder with no institution word is dropped."""
    for span in model_spans:
        span = span.strip()
        if span and len(span) < len(institution) and institution.lower().startswith(span.lower() + " "):
            rest = institution[len(span):].strip(" ,")
            if len(rest.split()) <= 2 and not _INSTITUTION_KEYWORD_RE.search(rest) and rest[:1].isupper():
                return span
    city = _TRAILING_CITY_RE.search(institution)
    if city and len(institution[: city.start()].split()) >= 2:
        return institution[: city.start()].rstrip(" ,-")
    return institution


# Cities resumes write straight after an institution's name ("... Institute of
# Technology Bengaluru"). A short list of the usual ones is safer than guessing
# that any last capitalised word is a place ("... University of Texas").
_TRAILING_CITY_RE = re.compile(
    r"[\s,]+(?:bengaluru|bangalore|mumbai|delhi|new delhi|chennai|hyderabad|pune|kolkata|ahmedabad|noida|gurgaon|"
    r"gurugram|mysuru|mysore|mangaluru|mangalore|jaipur|lucknow|chandigarh|kochi|coimbatore|nagpur|indore|bhopal|"
    r"surat|vellore|trichy|varanasi|dehradun|bhubaneswar|patna|guwahati)$",
    re.IGNORECASE,
)


_LEADING_DATE_RE = re.compile(
    r"^(?:(?:%s)\s+)?(?:19|20)\d{2}(?:\s*(?:-|–|—|to)\s*(?:(?:%s)\s+)?(?:(?:19|20)\d{2}|present|current))?\s+"
    % (_MONTH[: -len(r"\s+")], _MONTH[: -len(r"\s+")]),
    re.IGNORECASE,
)


def _strip_leading_date(piece: str) -> str:
    """"May 2000 Mississippi College" and "2016 Ecotect Institute" -> the institution alone."""
    stripped = _TRAILING_PLACE_WORD_RE.sub("", _LEADING_DATE_RE.sub("", piece)).strip()
    # "English Language 1999 University of Jos": a field and a year in front of the college.
    after_year = re.search(r"\b(?:19|20)\d{2}\b\s+(\S.*)$", stripped)
    if after_year and _INSTITUTION_KEYWORD_RE.search(after_year.group(1)):
        stripped = after_year.group(1).strip()
    return stripped if stripped and _INSTITUTION_KEYWORD_RE.search(stripped) else piece


def _drop_institution_from_degree(degree: str, institution: str) -> str:
    """A degree the model tagged together with its college ("M.Com (Master of Commerce) University of
    Kerala") without the college."""
    if institution:
        at = degree.lower().find(institution.lower())
        if at > 0:
            return degree[:at].strip(" ,-–—|:;")
    return degree


def _institution_in_line_excluding(line: str, degree: str) -> str:
    """Like _institution_in_line, but a piece that holds the degree itself
    ("Bachelor of Technology, College of Engineering" as one piece) is not an
    institution."""
    for piece in _INSTITUTION_SEPARATOR_RE.split(_BULLET_RE.sub("", line)):
        piece = _strip_leading_date(piece.strip(" ."))
        if _DEGREE_START_RE.match(piece):
            # "M.Com (Master of Commerce) University of Kerala": the college follows the closing bracket.
            tail = re.search(r"\)\s+([A-Z][^()]*)$", piece)
            if tail and _INSTITUTION_KEYWORD_RE.search(tail.group(1)):
                return tail.group(1).strip(" .")
            continue
        if _INSTITUTION_KEYWORD_RE.search(piece) and _norm(degree) not in _norm(piece):
            return piece
    return ""


# Text that went through the wrong character set on the way out of a PDF: UTF-8 bytes read as
# Windows-1252 ("â€“" for an en dash, a stray "Â" before a no-break space, "ï¼" + a control
# character for a full-width hyphen). The leftovers glue themselves onto institution and company
# names, so they are put right before anything reads the text.
_MOJIBAKE = {
    "â€“": "–", "â€”": "—", "â€™": "'", "â€˜": "'", "â€œ": '"', "â€\x9d": '"', "â€¢": "•", "â€¦": "...",
    "Â·": "·", "Â\xa0": " ", "Â ": " ", "Â": "",
}
_FULLWIDTH_HYPHEN_RE = re.compile("ï¼[\u200b\x8d\ufeff]?")


def fix_mojibake(text: str) -> str:
    """The text with the usual wrong-character-set leftovers repaired."""
    if "Â" not in text and "â€" not in text and "ï¼" not in text:
        return text
    text = _FULLWIDTH_HYPHEN_RE.sub(" - ", text)
    for broken, fixed in _MOJIBAKE.items():
        text = text.replace(broken, fixed)
    return text


@lru_cache(maxsize=1)
def _occupation_words() -> frozenset[str]:
    """Words that appear in the catalogue's role titles ("nurse", "generalist", "representative")
    plus the generic title nouns: a first line made of them is a job title, not a person."""
    from app.config import DATA_DIR

    words: set[str] = set(_TITLE_NOUNS.split("|"))
    for name in ("role_skills.json", "role_skills_general.json"):
        with open(DATA_DIR / name, encoding="utf-8") as f:
            for role in json.load(f):
                words.update(w for w in re.findall(r"[a-z]+", role["role"].lower()) if len(w) >= 4)
    words.update({"professional", "executive", "senior", "junior", "general", "certified", "licensed", "registered"})
    return frozenset(words)


# ---------------------------------------------------------------------------
# Line-based repair passes. The model tags spans, but on real resumes it cuts
# spans short ("Machine Learning" for "Machine Learning Engineer", "(BCA" for
# "(BCA)"), skips a title or a degree altogether, and glues grade labels onto a
# degree. The resume's own lines are the reliable source for all of these, so
# each pass below reads the section text line by line and only ever adds
# what a line clearly says.
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^[\s\-–—•●▪◦*·>]+")
# Where a degree's own words stop and grade/date/place information begins.
_GRADE_TAIL_RE = re.compile(
    r"[\s,;:|(\[-]*(?:\b(?:c\.?g\.?p\.?a|c\.?p\.?i|s\.?g\.?p\.?a|g\.?p\.?a|percentage|percent|grade|score|marks|aggregate|cgpa)\b"
    r"|\d+(?:\.\d+)?\s*(?:%|/\s*10\b|/\s*4\b)|\b(?:19|20)\d{2}\b).*$",
    re.IGNORECASE,
)
# A degree written at the start of a piece of an education line. Long words are
# case-insensitive; the short abbreviations ("BE", "ME", "MA") are
# case-sensitive so ordinary words never match.
_DEGREE_LONG = (
    r"(?:bachelors?|masters?|doctorate|doctor of|post[- ]?graduate|diploma|associate degree|higher secondary|"
    r"senior secondary|secondary school|intermediate\b(?!\s+(?-i:[a-z]))|pre[- ]?university|(?:10|12)th\b|class (?:x|xii)\b|"
    r"high school|general education diploma|ged\b|"
    r"(?:hsc|ssc|sslc|icse|cbse|pgdm|pgdca)\b)"
)
_DEGREE_SHORT = (
    r"(?:B\.?\s?Tech|M\.?\s?Tech|B\.?\s?E\b|M\.?\s?E\b|B\.?\s?Sc|M\.?\s?Sc|B\.?\s?Com|M\.?\s?Com|B\.?\s?C\.?A\b|M\.?\s?C\.?A\b|"
    r"BBA|MBA|B\.?\s?A\b|M\.?\s?A\b|Ph\.?\s?D|LLB|LLM|MBBS|B\.?\s?Pharm|M\.?\s?Pharm|B\.?\s?Arch|M\.?\s?Arch|BS|MS)"
)
_DEGREE_START_RE = re.compile(rf"^(?:(?i:{_DEGREE_LONG})|{_DEGREE_SHORT})")
_TITLE_NOUNS = (
    "engineer|developer|intern|manager|analyst|scientist|architect|consultant|designer|administrator|lead|specialist|"
    "executive|officer|associate|director|trainee|programmer|tester|researcher|assistant|head|president|technician|"
    "coordinator|internship|apprentice|fellow|sde|sde-1|sde-2|devops|owner|strategist|writer|recruiter|accountant"
)
_TITLE_END_RE = re.compile(rf"\b(?:{_TITLE_NOUNS})s?\b[\s.)]*(?:i{{1,3}}|[1-3])?$", re.IGNORECASE)
_TITLE_ANY_RE = re.compile(rf"\b(?:{_TITLE_NOUNS})s?\b", re.IGNORECASE)
_EXP_PIECE_SPLIT_RE = re.compile(r"\s+[-–—|@·•]\s+|\s+at\s+|\s*[|•·]\s*|,\s+|\t|\s{3,}")
_MAX_TITLE_WORDS = 8


def _clean_lines(section_text: str) -> list[str]:
    return [line.strip() for line in section_text.splitlines() if line.strip()]


def _strip_grade(degree: str) -> str:
    """The degree without a trailing grade label or score ("MCA CPI" ->
    "MCA", "B.E. CGPA: 8.1" -> "B.E."). Never strips a degree down to nothing."""
    cleaned = _GRADE_TAIL_RE.sub("", degree).strip(" ;,:|-–")
    return cleaned or degree.strip()


def _balance_parenthesis(degree: str, line: str) -> str:
    """Completes a cut-off bracket: the model tags "Bachelor of Computer
    Applications (BCA" and leaves the ")" behind."""
    if degree.count("(") <= degree.count(")"):
        return degree
    at = line.lower().find(degree.lower())
    if at == -1:
        return degree + ")"
    close = line.find(")", at + len(degree))
    return line[at : close + 1].strip() if close != -1 and close - (at + len(degree)) < 12 else degree + ")"


def _degree_pieces(line: str) -> list[str]:
    """The pieces of one education line that start with a degree."""
    found = []
    for raw in _INSTITUTION_SEPARATOR_RE.split(_BULLET_RE.sub("", line)):
        piece = raw.strip(" .;:")
        if piece and _DEGREE_START_RE.match(piece):
            found.append(piece)
    return found


def _recover_missing_degrees(education: list[EducationEntry], education_section_text: str) -> list[EducationEntry]:
    """Adds a record for each degree line no entry accounts for (the model
    simply did not tag it), and puts all records in the order of the lines.
    The institution and year of an added record are filled by the passes that
    follow, like for any other record."""
    if not education_section_text:
        return education
    lines = _clean_lines(education_section_text)

    def line_of(entry: EducationEntry) -> int | None:
        for key in (entry.degree, entry.institution):
            key = key.strip().lower()
            if key:
                for index, line in enumerate(lines):
                    if key in line.lower():
                        return index
        return None

    covered = {index for entry in education if (index := line_of(entry)) is not None}
    for index, line in enumerate(lines):
        if index in covered:
            continue
        pieces = _degree_pieces(line)
        if not pieces:
            continue
        degree = _strip_grade(pieces[0])
        if len(degree.split()) > 12 or any(e.degree.strip().lower() == degree.lower() for e in education):
            continue
        education.append(EducationEntry(degree=degree, institution="", year=""))

    positions = {id(entry): line_of(entry) for entry in education}
    ranked = sorted(
        range(len(education)),
        key=lambda i: (positions[id(education[i])] is None, positions[id(education[i])] or 0, i),
    )
    return [education[i] for i in ranked]


def _repair_degrees(education: list[EducationEntry], education_section_text: str) -> list[EducationEntry]:
    """Closes cut-off brackets and removes glued grade labels ("MCA CPI")."""
    lines = _clean_lines(education_section_text)
    for entry in education:
        if not entry.degree:
            continue
        line = next((l for l in lines if entry.degree.lower() in l.lower()), "")
        entry.degree = _balance_parenthesis(entry.degree, line) if line else entry.degree
        entry.degree = _strip_grade(entry.degree)
    return education


def _line_pieces(line: str) -> list[str]:
    return [p.strip(" .;:()") for p in _EXP_PIECE_SPLIT_RE.split(_BULLET_RE.sub("", line)) if p.strip(" .;:()")]


def _looks_like_title(piece: str) -> bool:
    words = piece.split()
    return (
        0 < len(words) <= _MAX_TITLE_WORDS
        and not re.search(r"\d{3,}", piece)
        and piece[0].isupper()
        and bool(_TITLE_END_RE.search(piece))
    )


def _repair_experience(
    experience: list[ExperienceEntry], experience_text: str, allow_new_records: bool
) -> list[ExperienceEntry]:
    """Completes cut-off titles, fills the title of a record the model found
    only a company for, adds jobs the model skipped, and orders jobs as they
    are written."""
    lines = _clean_lines(experience_text)
    if not lines:
        return experience

    # 1. A title the model cut short -> the whole title as written on its line.
    for entry in experience:
        title = entry.title.strip()
        if not title:
            continue
        all_pieces = [piece for line in lines for piece in _line_pieces(line)]
        # A title that is written in full somewhere is not cut short, even if
        # it is also the start of another job's title ("Software Engineer" /
        # "Software Engineering Intern").
        if not any(piece.lower() == title.lower() for piece in all_pieces):
            wider = [
                piece
                for piece in all_pieces
                if len(piece) > len(title)
                and piece.lower().startswith(title.lower() + " ")
                and _looks_like_title(piece)
            ]
            if len(set(w.lower() for w in wider)) == 1:
                title = wider[0]
        entry.title = title

    # 2. A record with a company and no title -> the title on the company's line
    #    (or just above it when the company has a line of its own).
    for entry in experience:
        if entry.title or not entry.organization:
            continue
        org = entry.organization.strip().lower()
        for index, line in enumerate(lines):
            if org not in line.lower():
                continue
            candidates = [p for p in _line_pieces(line) if org not in p.lower()]
            if not any(_looks_like_title(p) for p in candidates) and index > 0:
                candidates = _line_pieces(lines[index - 1])
            entry.title = next((p for p in candidates if _looks_like_title(p)), "")
            break

    # 2a. A company the model cut short ("Solutions" for "Mu Sigma Business
    #     Solutions") -> the whole plain piece it ends (never one it starts: that would
    #     take a city written after the company).
    for entry in experience:
        org = entry.organization.strip()
        if not org:
            continue
        pieces = [piece for line in lines for piece in _line_pieces(line)]
        if any(piece.lower() == org.lower() for piece in pieces):
            continue
        wider = {
            piece
            for piece in pieces
            if len(piece) > len(org)
            and 0 < len(piece.split()) <= 6
            and not re.search(r"\d", piece)
            and piece.lower().endswith(" " + org.lower())
            and not _TITLE_ANY_RE.search(piece)
        }
        if len(wider) == 1:
            entry.organization = wider.pop()

    # 2b. A title with no company -> the company on the same line (another
    #     piece) or on the line below, when that line is short and plain.
    for entry in experience:
        if entry.organization or not entry.title:
            continue
        for index, line in enumerate(lines):
            if entry.title.lower() not in line.lower():
                continue
            def plain(piece: str) -> bool:
                return (
                    0 < len(piece.split()) <= 6
                    and not re.search(r"\d", piece)
                    and piece[0].isupper()
                    and not _TITLE_ANY_RE.search(piece)
                    and piece.lower() != entry.title.lower()
                )
            same = [p for p in _line_pieces(line) if plain(p) and entry.title.lower() not in p.lower()]
            if same:
                entry.organization = same[0]
            elif index + 1 < len(lines) and not (lines[index + 1].lstrip()[0] in "-–—•●▪◦*·>"):
                below = _line_pieces(lines[index + 1])
                if below and plain(below[0]):
                    entry.organization = below[0]
            if not entry.organization:
                # "Company  Remote" on the line above the title, with a lone
                # bullet between them: take the nearest text line above.
                for above in reversed(lines[:index]):
                    pieces = _line_pieces(above)
                    if not pieces:
                        continue  # a bullet-only line
                    if plain(_strip_work_mode(pieces[0])) and not _DATE_RANGE_RE.search(above):
                        entry.organization = _strip_work_mode(pieces[0])
                    break
            break

    # 3. A job the model skipped entirely: a line that is a title and names its
    #    company in the same line or the one below.
    if allow_new_records:
        known = [e.title.lower() for e in experience if e.title] + [e.organization.lower() for e in experience if e.organization]
        for index, line in enumerate(lines):
            if _BULLET_RE.match(line) and line.lstrip()[0] in "-–—•●▪◦*·>":
                continue
            pieces = _line_pieces(line)
            title = next((p for p in pieces if _looks_like_title(p)), None)
            if title is None or any(title.lower() == k or title.lower() in k for k in known):
                continue
            others = [p for p in pieces if p != title and not re.search(r"\d{4}", p) and 0 < len(p.split()) <= 6]
            if not others and index + 1 < len(lines):
                nxt = lines[index + 1]
                if not _BULLET_RE.match(nxt) or nxt.lstrip()[0] not in "-–—•●▪◦*·>":
                    others = [p for p in _line_pieces(nxt) if not re.search(r"\d{4}", p) and 0 < len(p.split()) <= 6][:1]
            if others and not _TITLE_ANY_RE.search(others[0]):
                experience.append(ExperienceEntry(title=title, organization=others[0], duration="", description=""))
                known.extend([title.lower(), others[0].lower()])

    # Records that ended up with neither a title nor a company carry nothing.
    experience = _clean_experience([e for e in experience if e.title])

    def position(entry: ExperienceEntry) -> int:
        lowered = experience_text.lower()
        spots = [lowered.find(k.lower()) for k in (entry.title, entry.organization) if k]
        spots = [s for s in spots if s != -1]
        return min(spots) if spots else len(lowered)

    experience.sort(key=position)
    return experience


_WORK_MODE_RE = re.compile(r"\s+(?:remote|hybrid|on-?site)$", re.IGNORECASE)


def _strip_work_mode(text: str) -> str:
    """A company without the work-mode word written after it ("Deradh Remote")."""
    stripped = _WORK_MODE_RE.sub("", text.strip())
    return stripped or text.strip()


# Words a resume template (or an anonymiser) leaves where the real company or place was.
_PLACEHOLDER_ORGANIZATIONS = {"state", "city", "company name", "company", "name", "abc", "xyz", "abc company", "location"}


_COMPANY_NAME_PLACEHOLDER_RE = re.compile(r"\b(?:(?:current|previous|former)\s+)?company\s+name\b", re.IGNORECASE)
_TRAILING_PLACE_WORD_RE = re.compile(r"\s+(?:city|state)\s*$", re.IGNORECASE)
# One-word "titles" the model picks out of running text.
_GENERIC_TITLE_WORDS = {"general", "summary", "experience", "highlights", "company", "state", "city", "current"}


_PHRASE_START_WORDS = {"in", "on", "at", "the", "a", "an", "to", "of", "and", "or", "with", "for", "by", "this", "that", "our"}
_PHRASE_MIDDLE_WORDS = {"with", "for", "by", "that", "which", "to"}


def _looks_like_phrase(text: str) -> bool:
    """A piece of a sentence rather than a job title or a company: "MANAGED", "Collaborates with
    project managers", "Maintained up-to-date employee spreadsheet", "In this small"."""
    words = text.lower().split()
    if not words:
        return False
    first = words[0].strip(".,;:")
    return (
        first in _PHRASE_START_WORDS
        or (first.endswith("ed") and len(first) > 4)
        or (len(words) >= 3 and any(w in _PHRASE_MIDDLE_WORDS for w in words[1:]))
        or len(words) > 9
    )


def _clean_experience(experience: list[ExperienceEntry]) -> list[ExperienceEntry]:
    """Drops the junk the model's half-tagged titles leave ("A", "/"), trims dangling separators
    off titles ("Food Services Director/"), blanks placeholder companies ("State", "Company
    Name"), and merges a record repeated with the same title and company."""
    cleaned: list[ExperienceEntry] = []
    seen: set[tuple[str, str]] = set()
    for entry in experience:
        entry.title = entry.title.strip(" /-–—|:;,.")
        if sum(char.isalpha() for char in entry.title) < 3 or _looks_like_phrase(entry.title):
            continue
        organization = _COMPANY_NAME_PLACEHOLDER_RE.sub("", entry.organization)
        organization = _TRAILING_PLACE_WORD_RE.sub("", organization).strip(" /-–—|:;,.")
        if organization.lower() in _PLACEHOLDER_ORGANIZATIONS or organization.lower() in entry.title.lower():
            organization = ""  # a placeholder, or just the tail of the title ("Clerk" in "Accounting Clerk")
        entry.organization = "" if _looks_like_phrase(organization) else organization
        if entry.title.lower() in _GENERIC_TITLE_WORDS and not entry.organization:
            continue
        key = (entry.title.lower(), entry.organization.lower())
        if key in seen and not entry.duration:
            continue
        seen.add(key)
        cleaned.append(entry)
    return cleaned


def _fill_missing_durations(experience: list[ExperienceEntry], text: str) -> list[ExperienceEntry]:
    """Durations for jobs added by the repair passes: the nearest date range
    to the job's title or company that no other job has taken."""
    matches = list(_DATE_RANGE_RE.finditer(text))
    used = {e.duration for e in experience if e.duration}
    for entry in experience:
        if entry.duration:
            continue
        anchors = [text.find(k) for k in (entry.title, entry.organization) if k]
        anchors = [a for a in anchors if a != -1]
        if not anchors:
            continue
        free = [m for m in matches if m.group(0) not in used and min(abs(m.start() - a) for a in anchors) <= _MAX_DATE_MATCH_DISTANCE_CHARS]
        if free:
            best = min(free, key=lambda m: min(abs(m.start() - a) for a in anchors))
            entry.duration = best.group(0)
            used.add(entry.duration)
    return experience


_NAME_PARTICLES = {
    "van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "la", "le", "bin", "bint", "ibn", "al", "el",
    "ben", "bar", "dos", "das", "y", "e", "st", "ter", "ten",
}
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md"}
_NAME_MAX_WORDS = 6
# Where a name ends on a line that also holds contact details.
_NAME_CUT_RE = re.compile(r"\s*[|•·●▪]\s*|\t|\s{3,}|\s[-–—]\s|\s*[<(\[]")


def _extract_name(text: str) -> str:
    """The candidate's name, taken from the first few non-empty lines of the
    resume, or "" if none of them looks like a name. Resumes put the name on
    the first line nearly always, but when headings are present the NER
    model never sees the top of the resume (see parse_resume_local), so it
    can't tag the name there.

    A line (cut where contact details start: "Name | email | phone") counts
    as a name when it is 2-6 words of letters, each capitalised or ALL CAPS
    (lower-case particles like "van", "bin", "de" and suffixes like "Jr" are
    allowed inside), and none of them is a word that marks a heading or a job
    title ("Resume", "Experience", "Engineer", ...). Initials ("A. K. Biswas")
    count as words.
    """
    lines = (" ".join(line.split()) for line in text.splitlines())
    for line in [line for line in lines if line][:_NAME_SEARCH_LINES]:
        candidate = _NAME_CUT_RE.split(line, maxsplit=1)[0].strip(" ,.")
        words = candidate.split(" ")
        if not 2 <= len(words) <= _NAME_MAX_WORDS or "@" in candidate:
            continue
        cleaned = [w.lower().strip(".,") for w in words]
        if any(w in _NOT_NAME_WORDS for w in cleaned):
            continue
        if any(w in _occupation_words() for w in cleaned):
            continue  # "HR GENERALIST", "PROFESSIONAL HEALTHCARE REPRESENTATIVE": a job title, not a name
        if not _NAME_LINE_RE.fullmatch(candidate):  # a comma ("Pune, India") is a place, not a name
            continue
        content = [w for w, c in zip(words, cleaned) if c not in _NAME_PARTICLES and c not in _NAME_SUFFIXES]
        if len(content) >= 2 and all(w[0].isupper() for w in content):
            return candidate
    return _single_word_name(text)


def _single_word_name(text: str) -> str:
    """A name written as one word ("Amrutha") alone on the first line, accepted
    only when contact details (an email or a phone number) follow within the
    next two lines, which a stray one-word heading would not have."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()][:3]
    if len(lines) < 2:
        return ""
    first = lines[0]
    if (
        re.fullmatch(_NAME_WORD, first)
        and 3 <= len(first) <= 25
        and first[0].isupper()
        and first.lower().strip(".") not in _NOT_NAME_WORDS
        and any("@" in line or _PHONE_RE.search(line) for line in lines[1:])
    ):
        return first
    return ""


# Single words the model tags as "Skills" that name no skill ("Data" from
# "Data Science Trainee").
_GENERIC_SKILL_WORDS = {
    "data", "skills", "skill", "technologies", "technology", "tools", "software", "systems", "development",
    "experience", "knowledge", "programming", "languages", "projects", "training", "analysis", "management",
}


_SKILL_LIST_DELIMITER_RE = re.compile(r"[,|;•●▪·\n]+")
_SKILL_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z &/()+.-]{0,45}:\s*")
_MAX_SKILL_WORDS = 5


def _split_outside_brackets(text: str) -> list[str]:
    """Splits on the skill-list delimiters, but not on one inside brackets:
    "Google Cloud (Firebase, Gemini API, IAM)" is one item that holds three."""
    parts, depth, current = [], 0, []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and _SKILL_LIST_DELIMITER_RE.fullmatch(char):
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _skills_from_section(skills_text: str) -> list[str]:
    """The skills written in the resume's Skills section. The NER model only
    reads Experience and Education and the dictionary only knows the skills in
    the taxonomy, so a skill such as "Prompt Engineering" or "SOC" listed here
    was never picked up. Each line may carry a label ("Cloud: AWS, Azure");
    items are split on commas, bars and bullets (not inside brackets); a
    bracket that lists several things ("Google Cloud (Firebase, IAM)") gives
    each of them, and a bracket that is only an abbreviation ("(DSA)") is
    dropped. Anything longer than a skill name (a sentence) is ignored.
    """
    found = []
    # A PDF wraps a long skill ("Alternative Dispute\nResolution (ADR)"): a line that starts in
    # lower case or with a bracket, or follows one that ends with "&", "and" or "/", is the same item.
    skills_text = re.sub(r"(?:(?<=&)|(?<=/)|(?<= and))\s*\n\s*|(?<![.,;:•|])\n\s*(?=[a-z(])", " ", skills_text)
    # ... and so is the next line of a comma-separated list cut mid-item at the page width: a
    # long list line that does not end in a delimiter and is not followed by a "Label:" row.
    skills_text = re.sub(
        r"(?m)^([^\n]{60,}[^\s,;.:•|])\n(?!\s*[A-Za-z][A-Za-z &/()+.-]{0,45}:)(?=\S)",
        lambda m: m.group(1) + " " if re.search(r"[,;]", m.group(1)) else m.group(0),
        skills_text,
    )
    for line in skills_text.splitlines():
        line = _SKILL_LABEL_RE.sub("", _BULLET_RE.sub("", line.strip()))
        for raw in _split_outside_brackets(line):
            inner = re.search(r"\(([^)]*)\)", raw)
            candidates = [re.sub(r"\s*\([^)]*\)?", "", raw)]
            if inner and "," in inner.group(1):
                candidates += inner.group(1).split(",")
            for candidate in candidates:
                item = candidate.strip(" .:-–()")
                if (
                    item
                    and len(item.split()) <= _MAX_SKILL_WORDS
                    and item.lower() not in _GENERIC_SKILL_WORDS
                    and not _looks_like_sentence_fragment(item)
                ):
                    found.append(item)
    return found


def _looks_like_sentence_fragment(item: str) -> bool:
    """"Mentored numerous new team members", "etc", "the district": a phrase from a sentence, not a skill."""
    words = item.lower().split()
    first = words[0]
    return (
        item.lower() in {"etc", "etc.", "additional information"}
        or (len(words) >= 3 and any(w in {"to", "for", "but", "not", "that", "which", "with"} for w in words[1:]))
        or first in {"the", "a", "an", "to", "of", "and", "or", "with", "for", "into", "in", "on"}
        or (len(words) >= 3 and first.endswith("ed") and len(first) > 4)
    )


def _split_skill_spans(spans: list[str]) -> list[str]:
    """Split each raw "Skills" entity span on common list delimiters. Only
    does splitting/trimming -- normalize_skills() (reused, not reimplemented)
    already handles lowercasing, taxonomy mapping, and de-duplication.
    """
    pieces = []
    for span in spans:
        for piece in _SKILL_DELIMITER_RE.split(span):
            piece = piece.strip(" .")
            if piece and piece.lower() not in _GENERIC_SKILL_WORDS:
                pieces.append(piece)
    return pieces


def _extract_email(text: str) -> str:
    """Return the first regex-matched email address in text, or "" if none."""
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else ""


def _extract_phone(text: str) -> str:
    """Return the first regex-matched phone number in text, or "" if none."""
    match = _PHONE_RE.search(text)
    return match.group(0) if match else ""
