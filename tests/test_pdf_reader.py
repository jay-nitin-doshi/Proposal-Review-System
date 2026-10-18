import pymupdf as fitz

from src.pdf_reader import extract_pdf


def make_pdf(text=None):
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_extracts_page_aware_text():
    extracted = extract_pdf(make_pdf("Supplier manufacturing capability proposal."))
    assert extracted.page_count == 1
    assert "[Page 1]" in extracted.text
    assert "manufacturing capability" in extracted.text
    assert extracted.extraction_status == "text_extracted"
    assert not extracted.warnings


def test_detects_scanned_or_empty_pdf():
    extracted = extract_pdf(make_pdf())
    assert extracted.extraction_status == "scanned_or_empty"
    assert "SCANNED_OR_EMPTY_PDF_REQUIRES_OCR_OR_MANUAL_REVIEW" in extracted.warnings


def test_rejects_empty_upload():
    import pytest

    with pytest.raises(ValueError, match="empty"):
        extract_pdf(b"")
