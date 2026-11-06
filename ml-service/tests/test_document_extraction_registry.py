"""Tests the format-dispatch factory in registry.py."""

import pytest

from app.services.document_extraction.base import UnsupportedDocumentTypeError
from app.services.document_extraction.pdf_extractor import PdfTextExtractor
from app.services.document_extraction.registry import get_extractor_for_filename


def test_pdf_filename_returns_pdf_extractor():
    extractor = get_extractor_for_filename("resume.pdf")

    assert isinstance(extractor, PdfTextExtractor)


def test_pdf_extension_match_is_case_insensitive():
    extractor = get_extractor_for_filename("resume.PDF")

    assert isinstance(extractor, PdfTextExtractor)


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedDocumentTypeError):
        get_extractor_for_filename("resume.odt")


def test_no_extension_raises():
    with pytest.raises(UnsupportedDocumentTypeError):
        get_extractor_for_filename("resume")
