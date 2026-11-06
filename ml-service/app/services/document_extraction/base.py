"""Shared contract for turning a resume file's raw bytes into plain text.
One concrete implementation per file format (see pdf_extractor.py), picked
at runtime by registry.py -- follows the same Protocol-based, Open/Closed
shape as LLMClient in llm_client.py (see CLAUDE.md, "Design principles").
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractedText:
    """A file's readable text plus how many words were left out of it
    because a reader could not see them (white, tiny or off-page text in a
    PDF) -- the ATS "no_hidden_text" check reports that count, since hidden
    text is how keyword stuffing and prompt injection get into a resume.
    """

    text: str
    hidden_word_count: int = 0


class DocumentTextExtractor(Protocol):
    """Anything that can turn a resume file's raw bytes into plain text, in
    correct reading order. Implemented once per supported file format.
    """

    def extract(self, file_bytes: bytes) -> ExtractedText:
        """Return the file's visible text content, reordered into correct
        reading order where the format's structure requires it (e.g.
        multi-column PDFs).
        """
        ...


class UnsupportedDocumentTypeError(Exception):
    """Raised by registry.get_extractor_for_filename() when no extractor is
    registered for a given file's extension (e.g. .doc or .odt).
    """
