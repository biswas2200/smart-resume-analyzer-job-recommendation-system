"""PDF implementation of DocumentTextExtractor. Split into an "impure" layer
(PdfTextExtractor.extract, which does real file I/O via pdfplumber) and a
pure layer (_reorder_words_into_text and its helpers), so the actual
layout-awareness logic can be tested with hand-built word lists -- no real
PDF file needed -- mirroring the impure/pure split already used in
local_ner_parser.py.
"""

import io

from app.services.document_extraction.base import ExtractedText

# Hidden-text rules (_split_hidden_words). Text smaller than this many points
# is unreadable on a printed or rendered page -- footnotes sit around 6-8 pt
# -- so anything under it is treated as hidden, as is text placed entirely
# outside the page and text whose fill colour is white or nearly so (each
# colour channel within this much of white). White text on a dark filled
# shape (a coloured header bar) is visible and kept.
_MIN_VISIBLE_FONT_SIZE = 3.0
_NEAR_WHITE_TOLERANCE = 0.05

# Words within this many PDF points of vertical difference are treated as
# being on the same line. 3.0 comfortably covers normal font-size line
# height variation without merging genuinely separate lines.
_LINE_TOP_TOLERANCE = 3.0

# The vertical strip (as a fraction of page width) checked for a column
# gutter. A resume with two columns (e.g. a skills sidebar next to the main
# content) almost always has a visible gap somewhere in the middle third of
# the page; a single-column resume has words spread across this whole
# strip.
_COLUMN_GUTTER_LEFT_FRACTION = 0.4
_COLUMN_GUTTER_RIGHT_FRACTION = 0.6

# If more than this fraction of a page's words cross the middle strip, the
# page is treated as single-column rather than two-column -- a real gutter
# should have very few, ideally zero, words overlapping it.
_MAX_GUTTER_OVERLAP_FRACTION = 0.05


class PdfTextExtractor:
    """DocumentTextExtractor for PDF files, using pdfplumber. Reorders each
    page's words into column-aware reading order before returning them as
    text, so a two-column resume's sections don't get interleaved -- see
    _reorder_words_into_text for the actual heuristic.
    """

    def extract(self, file_bytes: bytes) -> ExtractedText:
        """Extract all pages' visible text from a PDF's raw bytes,
        column-aware, counting the hidden words left out."""
        # Imported lazily so pdfplumber only needs to be installed when a
        # PDF is actually being parsed, matching the lazy-import pattern
        # already used for the groq/google-genai/transformers SDKs.
        import pdfplumber

        page_texts = []
        hidden_word_count = 0
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                # extra_attrs also splits a run of text wherever its colour
                # or size changes, so one hidden phrase never rides along
                # inside a visible word.
                words = page.extract_words(extra_attrs=["non_stroking_color", "size"])
                visible, hidden = _split_hidden_words(words, page.rects, page.width, page.height)
                hidden_word_count += hidden
                page_texts.append(_reorder_words_into_text(visible, page.width))
        return ExtractedText("\n\n".join(page_texts), hidden_word_count)


def _split_hidden_words(
    words: list[dict], rects: list[dict], page_width: float, page_height: float
) -> tuple[list[dict], int]:
    """Pure function: the words a reader can see, and how many were hidden
    (see the _MIN_VISIBLE_FONT_SIZE comment for the rules). `rects` is
    pdfplumber's page.rects; only filled, non-white ones matter, as the
    dark backgrounds that make white text visible.
    """
    dark_fills = [
        r for r in rects
        if r.get("fill") and not _is_near_white(r.get("non_stroking_color"))
    ]
    visible: list[dict] = []
    hidden = 0
    for word in words:
        if _is_hidden(word, dark_fills, page_width, page_height):
            hidden += 1
        else:
            visible.append(word)
    return visible, hidden


def _is_hidden(word: dict, dark_fills: list[dict], page_width: float, page_height: float) -> bool:
    if word.get("size", _MIN_VISIBLE_FONT_SIZE) < _MIN_VISIBLE_FONT_SIZE:
        return True
    if word["x1"] <= 0 or word["x0"] >= page_width or word["bottom"] <= 0 or word["top"] >= page_height:
        return True
    if _is_near_white(word.get("non_stroking_color")):
        centre_x = (word["x0"] + word["x1"]) / 2
        centre_y = (word["top"] + word["bottom"]) / 2
        return not any(
            r["x0"] <= centre_x <= r["x1"] and r["top"] <= centre_y <= r["bottom"] for r in dark_fills
        )
    return False


def _is_near_white(color) -> bool:
    """True for a gray, RGB or CMYK fill colour (pdfplumber gives a tuple of
    1, 3 or 4 numbers) that is white or nearly so. Anything else -- no
    colour, a pattern name -- counts as not white."""
    if not isinstance(color, (tuple, list)) or not color:
        return False
    try:
        channels = [float(c) for c in color]
    except (TypeError, ValueError):
        return False
    if len(channels) == 4:  # CMYK: white is no ink at all
        return all(c <= _NEAR_WHITE_TOLERANCE for c in channels)
    if len(channels) in (1, 3):  # gray or RGB: white is full intensity
        return all(c >= 1 - _NEAR_WHITE_TOLERANCE for c in channels)
    return False


def _reorder_words_into_text(words: list[dict], page_width: float) -> str:
    """Pure function, no I/O -- reorders a page's words (pdfplumber
    extract_words() shape: {"text", "x0", "x1", "top", "bottom"}, plus
    whatever other keys pdfplumber includes, which are ignored here) into
    correct reading order.

    Kept as a simple, explainable heuristic rather than a full layout-
    detection model: detect whether the page looks like two columns (a
    largely-empty vertical strip near the page's middle, with words on both
    sides of it); if so, emit column 0 (left) in full, then column 1
    (right) in full, since a resume's side-by-side sections (e.g. a skills
    sidebar next to the main content) are independent reading sequences,
    not a left-then-right-per-line layout. Otherwise, treat the whole page
    as one column.
    """
    if not words:
        return ""

    if _looks_like_two_columns(words, page_width):
        split_x = page_width / 2
        left_words = [word for word in words if word["x0"] < split_x]
        right_words = [word for word in words if word["x0"] >= split_x]
        return _lines_from_words(left_words) + "\n\n" + _lines_from_words(right_words)

    return _lines_from_words(words)


def _looks_like_two_columns(words: list[dict], page_width: float) -> bool:
    """True if a vertical gutter is visible near the page's middle (few
    words overlap it) with real content on both sides of it.
    """
    gutter_left = page_width * _COLUMN_GUTTER_LEFT_FRACTION
    gutter_right = page_width * _COLUMN_GUTTER_RIGHT_FRACTION

    crossing_gutter = 0
    left_of_gutter = 0
    right_of_gutter = 0
    for word in words:
        if word["x0"] < gutter_right and word["x1"] > gutter_left:
            crossing_gutter += 1
        elif word["x1"] <= gutter_left:
            left_of_gutter += 1
        elif word["x0"] >= gutter_right:
            right_of_gutter += 1

    if left_of_gutter == 0 or right_of_gutter == 0:
        return False
    return (crossing_gutter / len(words)) < _MAX_GUTTER_OVERLAP_FRACTION


def _lines_from_words(words: list[dict]) -> str:
    """Group words into lines (by clustering close `top` values), sort each
    line's words left-to-right, sort lines top-to-bottom, and join into
    text. Returns "" for an empty word list (used for a page/column with no
    words in it).
    """
    if not words:
        return ""

    sorted_by_top = sorted(words, key=lambda word: word["top"])
    lines: list[list[dict]] = []
    for word in sorted_by_top:
        # Compared against the first word of the current line (not the
        # previous word) so small cumulative drift across a long line of
        # slightly-varying tops can't gradually merge it into the next
        # line.
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= _LINE_TOP_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])

    line_texts = []
    for line_words in lines:
        line_words.sort(key=lambda word: word["x0"])
        line_texts.append(" ".join(word["text"] for word in line_words))
    return "\n".join(line_texts)
