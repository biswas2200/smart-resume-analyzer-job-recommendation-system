"""Picks the right DocumentTextExtractor for a given filename. The single
place that needs to change when a new file format is supported -- adding a
format means writing its extractor module and adding one line to
_EXTRACTORS_BY_EXTENSION below, nothing else (see CLAUDE.md, "Design
principles").
"""

from pathlib import Path

from app.services.document_extraction.base import (
    DocumentTextExtractor,
    UnsupportedDocumentTypeError,
)
from app.services.document_extraction.docx_extractor import DocxTextExtractor
from app.services.document_extraction.pdf_extractor import PdfTextExtractor

_EXTRACTORS_BY_EXTENSION: dict[str, DocumentTextExtractor] = {
    ".pdf": PdfTextExtractor(),
    ".docx": DocxTextExtractor(),
}


def get_extractor_for_filename(filename: str) -> DocumentTextExtractor:
    """Return the DocumentTextExtractor registered for filename's extension
    (case-insensitive). Raises UnsupportedDocumentTypeError if no extractor
    is registered for it.
    """
    extension = Path(filename).suffix.lower()
    extractor = _EXTRACTORS_BY_EXTENSION.get(extension)
    if extractor is None:
        raise UnsupportedDocumentTypeError(
            f"No extractor registered for file extension '{extension}'"
        )
    return extractor
