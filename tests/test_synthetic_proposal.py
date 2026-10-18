from pathlib import Path

import pymupdf

from src.pdf_reader import extract_pdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_PATH = PROJECT_ROOT / "synthetic_calyxora_pharmaworks_proposal.pdf"


def test_synthetic_proposal_is_extractable_and_covers_all_criteria_and_gates():
    proposal = extract_pdf(PROPOSAL_PATH.read_bytes())
    assert proposal.page_count == 12
    assert proposal.extraction_status == "text_extracted"
    assert not proposal.warnings

    text = proposal.text.casefold()
    criteria = [
        "manufacturing capability & process control",
        "gmp, quality system & product quality",
        "regulatory readiness & documentation",
        "supply capacity & business continuity",
        "implementation & technology transfer",
        "commercial value & price transparency",
        "ehs, security & risk controls",
        "support, experience & references",
    ]
    gates = [
        "current site-specific manufacturing licence",
        "applicable gmp status and inspection disposition",
        "exact product scope and target-market requirements confirmed",
        "no unresolved critical quality/data-integrity finding",
        "quality agreement and audit rights",
    ]
    for item in [*criteria, *gates]:
        assert item in text
    assert "not a real supplier" in text
    assert "inr 37,440,000" in text


def test_every_synthetic_proposal_page_is_watermarked():
    with pymupdf.open(PROPOSAL_PATH) as document:
        assert len(document) == 12
        for page in document:
            text = page.get_text()
            assert (
                "FICTIONAL TRAINING ARTIFACT" in text
                or "SYNTHETIC TRAINING ARTIFACT" in text
            )
