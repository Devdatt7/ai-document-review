"""Trust score, status and end-to-end pipeline tests. Gemini is always faked."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import claims as claims_module
import verify
from main import app
from models import (ConsequenceLevel as L, DocumentScoreResult, DocumentStatus as S, EvidenceChunk,
                    EvidenceResult, PipelineResult, RiskFinding, VerificationResult, VerificationVerdict as V)
from pipeline import review_document
from scoring import calculate_evidence_coverage, calculate_trust_score, decide_status, score_document

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def finding(level, finding_id="F1"):
    return RiskFinding(finding_id=finding_id, consequence=level, priority_score=50, reason="r",
                       recommended_action="a")


def verdict(v, claim_id="C1"):
    return VerificationResult(claim_id=claim_id, verdict=v, explanation="x", confidence=0.9)


def evidence(claim_id, has_chunk):
    chunks = [EvidenceChunk(source_id="SRC1", page=1, chunk_id="SRC1-P1-C1", text="t", score=1.0)] if has_chunk else []
    return EvidenceResult(claim_id=claim_id, evidence_chunks=chunks)


# ---------- trust score ----------

def test_score_no_findings():
    assert calculate_trust_score([]) == 100


def test_score_one_low_finding():
    assert calculate_trust_score([finding(L.LOW)]) == 98


def test_score_high_finding():
    assert calculate_trust_score([finding(L.HIGH)]) == 88


def test_score_critical_finding():
    assert calculate_trust_score([finding(L.CRITICAL)]) == 75


def test_score_cannot_go_below_zero():
    assert calculate_trust_score([finding(L.CRITICAL, f"F{i}") for i in range(1, 8)]) == 0


# ---------- evidence coverage ----------

def test_evidence_coverage():
    found = [evidence("C1", True), evidence("C2", False), evidence("C3", True), evidence("C4", True)]
    assert calculate_evidence_coverage(found, 4) == 75.0


def test_evidence_coverage_zero_claims():
    assert calculate_evidence_coverage([], 0) == 0.0


# ---------- status ----------

def test_status_ready():
    assert decide_status([], [verdict(V.SUPPORTED)]) == S.READY


def test_status_review():
    assert decide_status([finding(L.HIGH)], [verdict(V.CONTRADICTED)]) == S.REVIEW


def test_status_blocked():
    assert decide_status([finding(L.HIGH), finding(L.CRITICAL, "F2")], []) == S.BLOCKED


def test_unsupported_claim_prevents_ready_even_without_findings():
    assert decide_status([], [verdict(V.UNSUPPORTED)]) == S.REVIEW


def test_unclear_claim_prevents_ready_even_without_findings():
    assert decide_status([], [verdict(V.UNCLEAR)]) == S.REVIEW


def test_critical_finding_causes_blocked_even_if_supported():
    assert decide_status([finding(L.CRITICAL)], [verdict(V.SUPPORTED)]) == S.BLOCKED


def test_score_document_counts_and_summary():
    result = score_document([finding(L.CRITICAL), finding(L.HIGH, "F2"), finding(L.LOW, "F3")],
                            [verdict(V.CONTRADICTED)], [evidence("C1", True)], 1)
    assert (result.critical_count, result.high_count, result.medium_count, result.low_count) == (1, 1, 0, 1)
    assert result.finding_count == 3 and result.trust_score == 61 and result.status == S.BLOCKED
    assert "not a probability" in result.summary


# ---------- fake Gemini for the whole pipeline ----------

DOC = (
    "Refunds are available within 30 days except for customized products.\n"
    "The maximum reimbursement is ₹50,000.\n"
    "The policy is effective from 1 April 2026.\n"
    "Our company guarantees 100% uptime.\n"
    "The office has free parking.\n"
    "Customer PAN: ABCDE1234F"
)
CLAIM_SCRIPT = [  # (sentence_id, claim_text, claim_type)
    ("S1", "Refunds are available within 30 days except for customized products.", "policy"),
    ("S2", "The maximum reimbursement is ₹50,000.", "financial"),
    ("S3", "The policy is effective from 1 April 2026.", "date"),
    ("S4", "Our company guarantees 100% uptime.", "commitment"),
    ("S5", "The office has free parking.", "general"),
]
VERIFY_SCRIPT = {  # only for claims the Python rules cannot decide
    "Refunds are available within 30 days except for customized products.":
        (V.SUPPORTED, "Refunds are available within 30 days of purchase."),
    "Our company guarantees 100% uptime.": (V.CONTRADICTED, "This is a target, not a guarantee."),
    "The office has free parking.":
        (V.CONTRADICTED, "Parking is available for visitors on the ground floor at a daily charge."),
}
SOURCE = (ROOT / "data" / "sources" / "refund_policy.txt").read_text(encoding="utf-8")


@pytest.fixture
def fake_llm(monkeypatch):
    def fake_claims(prompt, schema):
        return schema(claims=[{"sentence_id": s, "claim_text": t, "claim_type": ty} for s, t, ty in CLAIM_SCRIPT])

    def fake_verify(prompt, schema):
        results = []
        for index, (_, claim_text, _) in enumerate(CLAIM_SCRIPT, start=1):
            if claim_text not in prompt or claim_text not in VERIFY_SCRIPT:
                continue
            v, quote = VERIFY_SCRIPT[claim_text]
            chunk_id = next(line[1:line.index("]")] for line in prompt.splitlines()
                            if line.startswith("[") and quote in line)
            results.append({
                "claim_id": f"C{index}",
                "verdict": v,
                "explanation": "scripted",
                "evidence_chunk_ids": [chunk_id],
                "evidence_quote": quote,
                "confidence": 0.8,
            })
        return schema(results=results)

    monkeypatch.setattr(claims_module, "ask_llm_json", fake_claims)
    monkeypatch.setattr(verify, "ask_llm_json", fake_verify)


def test_pipeline_end_to_end_with_fake_llm(fake_llm):
    result = review_document(DOC, SOURCE)
    assert isinstance(result, PipelineResult)
    assert len(result.claims) == len(result.evidence) == len(result.verification_results) == 5
    assert [e.claim_id for e in result.evidence] == [c.claim_id for c in result.claims]
    assert result.status == result.score.status


def test_refund_policy_integration(fake_llm, caplog):
    caplog.set_level(logging.DEBUG)
    result = review_document(DOC, SOURCE)
    verdicts = {v.claim_id: v.verdict for v in result.verification_results}
    assert verdicts == {"C1": V.SUPPORTED, "C2": V.CONTRADICTED, "C3": V.CONTRADICTED,
                        "C4": V.CONTRADICTED, "C5": V.CONTRADICTED}

    assert result.status == S.BLOCKED
    assert result.score.trust_score < 50
    assert result.score.critical_count == 2  # the guarantee and the PAN
    assert result.score.evidence_coverage == 100.0

    by_claim = {f.claim_id: f for f in result.findings}
    assert by_claim["C2"].consequence == L.HIGH and by_claim["C3"].consequence == L.HIGH
    assert by_claim["C4"].consequence == L.CRITICAL
    assert "C1" not in by_claim  # supported and not risky: nothing to review

    # Ranked by priority, and nothing hidden.
    priorities = [f.priority_score for f in result.ranked_findings]
    assert priorities == sorted(priorities, reverse=True)
    assert len(result.ranked_findings) == len(result.findings) == 5

    # PAN only in masked form: not in the output and not in the logs.
    dump = result.model_dump_json()
    assert "ABCDE1234F" not in dump and "ABCDE1234F" not in caplog.text
    assert "AB*****34F" in dump


def test_pipeline_zero_claims_is_safe(monkeypatch):
    result = review_document("   ", SOURCE)  # no sentences: Gemini is never called
    assert result.claims == [] and result.score.trust_score == 100
    assert result.score.evidence_coverage == 0.0 and result.status == S.READY


def test_output_schema_is_stable(fake_llm):
    data = json.loads(review_document(DOC, SOURCE).model_dump_json())
    assert set(data) == {"sentences", "claims", "evidence", "verification_results", "findings",
                         "ranked_findings", "score", "status"}
    assert set(data["score"]) == set(DocumentScoreResult.model_fields) == {
        "trust_score", "evidence_coverage", "status", "summary", "finding_count",
        "critical_count", "high_count", "medium_count", "low_count"}


# ---------- endpoints ----------

def test_analyze_endpoint(fake_llm):
    response = client.post("/analyze", json={"document_text": DOC, "source_text": SOURCE})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BLOCKED" and data["score"]["critical_count"] == 2
    assert "ABCDE1234F" not in response.text


def test_analyze_without_key_returns_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("llm.load_dotenv", lambda *a, **k: None, raising=False)
    import llm
    llm._client.cache_clear()  # a client cached by an earlier live test would still hold the real key
    try:
        response = client.post("/analyze", json={"document_text": "Fees are 5.", "source_text": SOURCE})
    finally:
        llm._client.cache_clear()
    assert response.status_code == 502
    assert "detail" in response.json()


def test_analyze_rejects_bad_input():
    assert client.post("/analyze", json={"document_text": "x"}).status_code == 422
    bad_id = {"document_text": "x", "source_text": "y", "source_id": "bad-id"}
    assert client.post("/analyze", json=bad_id).status_code == 422


def test_existing_endpoints_still_work():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/claims/extract", json={"document_text": ""}).status_code == 200
    assert client.post("/risk/analyze", json={"document_text": "Hello."}).json()["total_findings"] == 0
    body = {"claim": {"claim_id": "C1", "sentence_id": "S1", "claim_text": "x", "claim_type": "general"},
            "evidence_chunks": []}
    assert client.post("/claims/verify", json=body).json()["verdict"] == "UNSUPPORTED"
    retrieve = {"claims": [], "source_id": "SRC1", "source_text": "hello"}
    assert client.post("/evidence/retrieve", json=retrieve).status_code == 200


# ---------- One privacy issue = one reviewer finding ----------

def _claim(claim_id, text, claim_type):
    from models import Claim
    return Claim(claim_id=claim_id, sentence_id="S1", claim_text=text, claim_type=claim_type)


def test_sensitive_claim_with_pii_gives_single_finding_and_keeps_verification():
    from models import ClaimType, RiskType
    from scoring import build_findings
    doc = "Customer PAN: ABCDE1234F"
    claims = [_claim("C1", doc, ClaimType.sensitive)]
    results = [verdict(V.UNSUPPORTED, "C1")]
    findings = build_findings(doc, claims, results)
    assert len(findings) == 1
    assert findings[0].risk_type == RiskType.SENSITIVE_DATA
    assert "ABCDE1234F" not in findings[0].model_dump_json()
    assert results[0].verdict == V.UNSUPPORTED  # verification result is untouched


def test_masked_sensitive_claim_with_pii_in_document_gives_single_finding():
    from models import ClaimType, RiskType
    from scoring import build_findings
    claims = [_claim("C1", "Customer PAN: AB*****34F", ClaimType.sensitive)]
    findings = build_findings("Customer PAN: ABCDE1234F", claims, [verdict(V.UNSUPPORTED, "C1")])
    assert [f.risk_type for f in findings] == [RiskType.SENSITIVE_DATA]


def test_ordinary_unsupported_claim_still_gets_a_finding():
    from models import ClaimType
    from scoring import build_findings
    claims = [_claim("C1", "The office has free parking.", ClaimType.general)]
    findings = build_findings("The office has free parking.", claims, [verdict(V.UNSUPPORTED, "C1")])
    assert len(findings) == 1
    assert findings[0].verdict == V.UNSUPPORTED and findings[0].claim_id == "C1"


def test_ordinary_unsupported_claim_still_flagged_when_document_also_has_pii():
    from models import ClaimType
    from scoring import build_findings
    doc = "The office has free parking. Customer PAN: ABCDE1234F"
    claims = [_claim("C1", "The office has free parking.", ClaimType.general)]
    findings = build_findings(doc, claims, [verdict(V.UNSUPPORTED, "C1")])
    assert len(findings) == 2
