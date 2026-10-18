"""Page-aware PDF text extraction with explicit size and OCR warnings."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf as fitz


MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_EXTRACTED_CHARS = 120_000


@dataclass
class ExtractedPdf:
    page_count: int
    page_texts: list[str]
    text: str
    extraction_status: str
    warnings: list[str]


def extract_pdf(content: bytes) -> ExtractedPdf:
    """Extract text while preserving page boundaries and detecting image-only PDFs."""
    if not content:
        raise ValueError("The uploaded PDF is empty.")
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 20 MiB upload limit.")
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError(f"Unable to open PDF: {exc}") from exc

    with document:
        if document.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit.")
        page_texts: list[str] = []
        for page in document:
            page_text = page.get_text("text")
            if not isinstance(page_text, str):
                raise TypeError("PDF text extractor returned a non-text page result.")
            page_texts.append(page_text.strip())
        extracted = "\n\n".join(
            f"[Page {page_number}]\n{text}"
            for page_number, text in enumerate(page_texts, start=1)
            if text
        )
        warnings: list[str] = []
        if len(extracted.strip()) < 40:
            warnings.append("SCANNED_OR_EMPTY_PDF_REQUIRES_OCR_OR_MANUAL_REVIEW")
            status = "scanned_or_empty"
        else:
            status = "text_extracted"
        if len(extracted) > MAX_EXTRACTED_CHARS:
            extracted = extracted[:MAX_EXTRACTED_CHARS]
            warnings.append("EXTRACTED_TEXT_TRUNCATED_AT_120000_CHARACTERS")
        return ExtractedPdf(
            page_count=document.page_count,
            page_texts=page_texts,
            text=extracted,
            extraction_status=status,
            warnings=warnings,
        )
