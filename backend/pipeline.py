"""Runs the review steps in order. Each step is an existing module; this file only connects them."""

from claims import extract_claims
from checks import mask_text
from ingest import load_text_source
from models import (Claim, EvidenceResult, PipelineResult, RiskFinding, VerificationResult)
from retrieval import retrieve_for_claims
from scoring import build_findings, rank_findings, score_document
from verify import verify_claim


def verify_all(claims: list[Claim], evidence: list[EvidenceResult]) -> list[VerificationResult]:
    """Verify each claim against ITS OWN evidence (evidence list is in the same order as claims)."""
    return [verify_claim(claim, found.evidence_chunks) for claim, found in zip(claims, evidence)]


def review_document(document_text: str, source_text: str, source_id: str = "SRC1") -> PipelineResult:
    """document -> claims -> evidence -> verdicts -> findings -> ranking -> score and status.

    Raises LLMError if Gemini is unavailable during claim extraction (we never pretend it ran).
    """
    extraction = extract_claims(document_text)                      # Gemini
    source = load_text_source(source_id, source_text)
    evidence = retrieve_for_claims(extraction.claims, source)       # BM25, no LLM
    verifications = verify_all(extraction.claims, evidence)         # rules + Gemini
    findings: list[RiskFinding] = build_findings(document_text, extraction.claims, verifications)
    ranked = rank_findings(findings)
    score = score_document(findings, verifications, evidence, len(extraction.claims))

    # Analysis is done on the real text; what we RETURN has sensitive values masked.
    return PipelineResult(
        sentences=[s.model_copy(update={"text": mask_text(s.text)}) for s in extraction.sentences],
        claims=[c.model_copy(update={"claim_text": mask_text(c.claim_text)}) for c in extraction.claims],
        evidence=[EvidenceResult(claim_id=e.claim_id, evidence_chunks=[
                      c.model_copy(update={"text": mask_text(c.text)}) for c in e.evidence_chunks])
                  for e in evidence],
        verification_results=[v.model_copy(update={"explanation": mask_text(v.explanation),
                                                    "evidence_quote": mask_text(v.evidence_quote)})
                              for v in verifications],
        findings=findings, ranked_findings=ranked, score=score, status=score.status,
    )
