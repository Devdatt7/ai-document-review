import pymupdf
import pytest
from fastapi.testclient import TestClient

from ingest import load_pdf_source, load_text_source
from main import app
from models import Claim, ClaimType
from retrieval import (
    chunk_source,
    recall_at_k,
    retrieve_evidence,
    retrieve_for_claims,
    tokenize,
)

# Synthetic source text: 4 paragraphs.
PARAGRAPHS = [
    "Refunds are available within 30 days of purchase. Customized products are not eligible for a refund.",
    "Reimbursement is capped at ₹50,000 per claim.",
    "The policy is effective from 1 April 2026.",
    "Support is available on weekdays from 9am to 6pm.",
]
SOURCE_TEXT = "\n\n".join(PARAGRAPHS)
SOURCE = load_text_source("SRC1", SOURCE_TEXT)


def make_claim(text, claim_id="C1"):
    return Claim(
        claim_id=claim_id, sentence_id="S1", claim_text=text, claim_type=ClaimType.general
    )


def make_pdf(pages_text):
    """Build a tiny text-based PDF in memory (one string per page)."""
    pdf = pymupdf.open()
    for text in pages_text:
        pdf.new_page().insert_text((72, 100), text)
    return pdf.tobytes()


# ---------- chunking ----------

def test_paragraph_chunking_keeps_text_unchanged():
    chunks = chunk_source(SOURCE)
    assert [c.text for c in chunks] == PARAGRAPHS


def test_chunking_handles_windows_line_endings_and_extra_blank_lines():
    source = load_text_source("SRC1", "First para.\r\n\r\n\r\n\nSecond para.\r\n")
    assert [c.text for c in chunk_source(source)] == ["First para.", "Second para."]


def test_empty_source_has_no_chunks():
    assert chunk_source(load_text_source("SRC1", "  \n\n ")) == []


# ---------- stable chunk IDs ----------

def test_chunk_ids_are_stable():
    ids = [c.chunk_id for c in chunk_source(SOURCE)]
    assert ids == ["SRC1-P1-C1", "SRC1-P1-C2", "SRC1-P1-C3", "SRC1-P1-C4"]
    assert ids == [c.chunk_id for c in chunk_source(SOURCE)]


def test_source_id_is_preserved():
    source = load_text_source("POLICY_A", "Hello there.")
    assert chunk_source(source)[0].source_id == "POLICY_A"
    assert chunk_source(source)[0].chunk_id == "POLICY_A-P1-C1"


# ---------- retrieval ----------

def test_exact_match_claim_finds_its_paragraph_first():
    claim = make_claim("Customized products are not eligible for a refund.")
    results = retrieve_evidence(claim, SOURCE)
    assert results[0].chunk_id == "SRC1-P1-C1"


def test_numeric_claim_matches_number_with_and_without_comma():
    assert tokenize("₹50,000") == tokenize("50000") == ["50000"]
    for text in ["The maximum reimbursement is ₹50,000.", "Reimbursement is 50000"]:
        assert retrieve_evidence(make_claim(text), SOURCE)[0].chunk_id == "SRC1-P1-C2"


def test_date_claim_finds_date_paragraph():
    claim = make_claim("The policy is effective from 1 April 2026.")
    assert retrieve_evidence(claim, SOURCE)[0].chunk_id == "SRC1-P1-C3"


def test_claim_with_no_useful_evidence_returns_nothing():
    claim = make_claim("The office has free parking.")
    assert retrieve_evidence(claim, SOURCE) == []


def test_claim_with_only_stopwords_returns_nothing():
    assert retrieve_evidence(make_claim("It is the"), SOURCE) == []


def test_multiple_claims_each_get_their_own_evidence():
    claims = [
        make_claim("Refunds are available within 30 days.", "C1"),
        make_claim("The maximum reimbursement is ₹50,000.", "C2"),
        make_claim("The office has free parking.", "C3"),
    ]
    results = retrieve_for_claims(claims, SOURCE)
    assert [r.claim_id for r in results] == ["C1", "C2", "C3"]
    assert results[0].evidence_chunks[0].chunk_id == "SRC1-P1-C1"
    assert results[1].evidence_chunks[0].chunk_id == "SRC1-P1-C2"
    assert results[2].evidence_chunks == []


def test_top_k_is_limited_and_ordered_best_first():
    source = load_text_source(
        "SRC1",
        "\n\n".join(
            [
                "Refund refund refund policy.",
                "Refund rules apply to customers.",
                "Unrelated shipping notes.",
                "A refund may take time.",
                "Another refund note about delays and many other long extra words here.",
            ]
        ),
    )
    results = retrieve_evidence(make_claim("refund policy"), source)
    scores = [r.score for r in results]
    assert len(results) == 3  # default top 3, even though 4 chunks match
    assert scores == sorted(scores, reverse=True)
    assert results[0].chunk_id == "SRC1-P1-C1"
    assert len(retrieve_evidence(make_claim("refund policy"), source, top_k=1)) == 1


def test_every_result_has_a_positive_score():
    for chunk in retrieve_evidence(make_claim("Refunds within 30 days"), SOURCE):
        assert isinstance(chunk.score, float) and chunk.score > 0


def test_retrieval_is_deterministic_and_ties_keep_source_order():
    source = load_text_source("SRC1", "Same words here.\n\nSame words here.")
    first = retrieve_evidence(make_claim("same words"), source)
    assert first == retrieve_evidence(make_claim("same words"), source)
    assert [c.chunk_id for c in first] == ["SRC1-P1-C1", "SRC1-P1-C2"]


def test_retrieval_does_not_modify_chunk_text():
    result = retrieve_evidence(make_claim("Refunds within 30 days"), SOURCE)[0]
    assert result.text == PARAGRAPHS[0]


# ---------- PDF ----------

def test_pdf_pages_are_read_with_page_numbers():
    source = load_pdf_source("PDF1", make_pdf(["Refunds within 30 days.", "Reimbursement is capped at 25000."]))
    assert [p.page for p in source.pages] == [1, 2]
    chunks = chunk_source(source)
    assert [c.chunk_id for c in chunks] == ["PDF1-P1-C1", "PDF1-P2-C1"]
    assert "Refunds within 30 days" in chunks[0].text


def test_pdf_retrieval_reports_the_page():
    source = load_pdf_source("PDF1", make_pdf(["Refunds within 30 days.", "Reimbursement is capped at 25000."]))
    best = retrieve_evidence(make_claim("The reimbursement cap is 25,000."), source)[0]
    assert best.page == 2 and best.chunk_id == "PDF1-P2-C1"


def test_bad_or_empty_pdf_gives_clear_error():
    with pytest.raises(ValueError, match="Could not open"):
        load_pdf_source("PDF1", b"this is not a pdf")
    blank = pymupdf.open()
    blank.new_page()
    with pytest.raises(ValueError, match="No text found"):
        load_pdf_source("PDF1", blank.tobytes())


# ---------- evaluation helper (Recall@1 / Recall@3) ----------

LABELLED = [
    (make_claim("Refunds are available within 30 days."), "SRC1-P1-C1"),
    (make_claim("Maximum reimbursement is ₹50,000."), "SRC1-P1-C2"),
    (make_claim("The policy starts on 1 April 2026."), "SRC1-P1-C3"),
    (make_claim("Support runs on weekdays 9am to 6pm."), "SRC1-P1-C4"),
]


def test_recall_is_perfect_on_easy_labelled_examples():
    assert recall_at_k(LABELLED, SOURCE, k=1) == 1.0
    assert recall_at_k(LABELLED, SOURCE, k=3) == 1.0


def test_recall_counts_misses_and_k3_is_never_worse_than_k1():
    examples = LABELLED + [(make_claim("The office has free parking."), "SRC1-P1-C1")]
    assert recall_at_k(examples, SOURCE, k=1) == pytest.approx(0.8)
    assert recall_at_k(examples, SOURCE, k=3) >= recall_at_k(examples, SOURCE, k=1)
    assert recall_at_k([], SOURCE, k=1) == 0.0


# ---------- API ----------

def test_endpoint_returns_evidence_with_scores():
    claim = make_claim("The maximum reimbursement is ₹50,000.").model_dump(mode="json")
    response = TestClient(app).post(
        "/evidence/retrieve",
        json={"claims": [claim], "source_id": "SRC1", "source_text": SOURCE_TEXT},
    )
    body = response.json()
    assert response.status_code == 200
    assert body[0]["claim_id"] == "C1"
    top = body[0]["evidence_chunks"][0]
    assert top["chunk_id"] == "SRC1-P1-C2" and top["score"] > 0 and top["page"] is None


def test_endpoint_rejects_bad_source_id():
    response = TestClient(app).post(
        "/evidence/retrieve", json={"claims": [], "source_id": "bad-id!", "source_text": "x"}
    )
    assert response.status_code == 422
