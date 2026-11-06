"""Resume file upload -> parsed profile / full analysis. Kept as its own
router, separate from analyze.py, since file handling (this file) and
text-in analysis (analyze.py) are distinct concerns -- the two endpoints
below just extract text and then delegate to the exact same pipeline
functions analyze.py's text-based endpoints use.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.models.schemas import AnalyzeResponse, ParseResponse
from app.services import pipeline
from app.services.document_extraction.base import ExtractedText, UnsupportedDocumentTypeError
from app.services.document_extraction.registry import get_extractor_for_filename
from app.services.parser import parse_resume

router = APIRouter()
log = logging.getLogger(__name__)


async def _extract_text(file: UploadFile) -> ExtractedText:
    try:
        extractor = get_extractor_for_filename(file.filename or "")
    except UnsupportedDocumentTypeError as error:
        log.warning("unsupported file type %r", _extension(file.filename))
        raise HTTPException(status_code=415, detail=str(error)) from error

    file_bytes = await file.read()
    extracted = extractor.extract(file_bytes)
    # The extension and sizes only: a file name often carries the person's name.
    log.info(
        "extracted %d chars (%d hidden words left out) from a %s file of %d bytes",
        len(extracted.text), extracted.hidden_word_count, _extension(file.filename), len(file_bytes),
    )
    return extracted


def _extension(filename: str | None) -> str:
    return Path(filename or "").suffix.lower() or "(none)"


@router.post("/parse-file", responses={415: {"description": "Unsupported file type"}})
async def parse_file(file: UploadFile) -> ParseResponse:
    """Extract text from an uploaded resume file (see
    document_extraction/registry.py for what's supported) and run it
    through the existing parse_resume() pipeline unchanged.
    """
    extracted = await _extract_text(file)
    return ParseResponse(profile=parse_resume(extracted.text))


@router.post("/analyze-file", responses={415: {"description": "Unsupported file type"}})
async def analyze_file(
    file: UploadFile, top_n: int = 3
) -> AnalyzeResponse:
    """File-upload counterpart to POST /analyze: extract text the same way
    parse_file() does, then run the exact same pipeline (services/
    pipeline.py) as analyze.py's analyze(), so a caller that only has the
    raw file (e.g. the backend, which never sees resume text) gets one round
    trip instead of extracting text itself.
    """
    extracted = await _extract_text(file)
    return pipeline.analyze_text(
        extracted.text, top_n=top_n, hidden_word_count=extracted.hidden_word_count,
    )
