"""Deterministic, whole-text skill detection against the canonical taxonomy
(FR-1.7): every canonical skill and its known variants (skill_taxonomy.json)
is tokenized once, then found by sliding a window over the resume text's own
token stream, longest phrase first. This finds every dictionary skill
mentioned anywhere in the resume -- not just inside a "Skills" section -- and
its results are merged with the NER model's own "Skills" entity spans in
local_ner_parser.py for recall (a phrase this taxonomy hasn't been curated
for yet still comes through via NER).

Token-level matching (not raw character/substring matching) is what makes
this safe from the "java" vs "javascript" trap: two different variant tokens
are never equal, so a token-for-token match is required in every case, with
no risk of one matching inside the other. The taxonomy's longest phrase is a
handful of tokens, so a bounded sliding window has the same O(n) complexity
envelope as Aho-Corasick (docs/lld.md's reference algorithm) for a taxonomy
this small, without needing a hand-rolled automaton or a new dependency.
"""

import json
import re
from functools import lru_cache

from app.config import DATA_DIR

TAXONOMY_PATH = DATA_DIR / "skill_taxonomy.json"
# The all-domain taxonomy built by scripts/build_general_catalogue.py. Kept
# as a separate file (and matched only when a caller asks for it) so the
# engineering path's output stays byte-for-byte what it was before the
# general catalogue existed (docs/editions-and-parity.md).
GENERAL_TAXONOMY_PATH = DATA_DIR / "skill_taxonomy_general.json"

# Keeps connector punctuation (".", "+", "#", "/", "-") attached to the
# alphanumeric run on either side, so "node.js", "c++", "ci/cd" and "t-sql"
# each tokenize as one token, matching how they appear in skill_taxonomy.json.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.+#/-][a-z0-9]+)*")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@lru_cache
def _phrase_lookup(taxonomy_path=TAXONOMY_PATH) -> tuple[dict[tuple[str, ...], str], int]:
    """Maps each taxonomy variant's token tuple to its canonical skill name,
    plus the longest phrase length present -- the bound find_skills()'s
    sliding window needs. Cached per taxonomy file.
    """
    with open(taxonomy_path, encoding="utf-8") as f:
        canonical_to_variants: dict[str, list[str]] = json.load(f)

    lookup: dict[tuple[str, ...], str] = {}
    max_len = 1
    for canonical, variants in canonical_to_variants.items():
        for phrase in (canonical, *variants):
            tokens = tuple(_tokenize(phrase))
            if not tokens:
                continue
            lookup[tokens] = canonical
            max_len = max(max_len, len(tokens))
    return lookup, max_len


def find_skills(text: str, taxonomy_path=TAXONOMY_PATH) -> list[str]:
    """Every canonical skill mentioned anywhere in text, in first-found
    order. At each token position the longest matching phrase wins (so "rest
    api" matches as one skill rather than leaving a dangling "api"), and a
    match consumes its tokens so the same mention is never double-counted.
    Matches against the engineering taxonomy unless another file is given
    (domain_classifier.py passes GENERAL_TAXONOMY_PATH).
    """
    lookup, max_len = _phrase_lookup(taxonomy_path)
    tokens = _tokenize(text)
    n = len(tokens)

    found: list[str] = []
    seen: set[str] = set()
    i = 0
    while i < n:
        canonical = None
        matched_len = 0
        for length in range(min(max_len, n - i), 0, -1):
            hit = lookup.get(tuple(tokens[i : i + length]))
            if hit is not None:
                canonical, matched_len = hit, length
                break

        if canonical is not None:
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
            i += matched_len
        else:
            i += 1

    return found
