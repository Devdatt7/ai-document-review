import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from claims import extract_claims
from ingest import load_text_source
from llm import LLMError
from models import (SOURCE_ID_PATTERN, Claim, ClaimExtractionResult, EvidenceChunk, EvidenceResult,
                    PipelineResult, RiskAnalysisResult, VerificationResult)
from pipeline import review_document
from retrieval import retrieve_for_claims
from scoring import build_findings, rank_findings
from verify import verify_claim

app = FastAPI(title="AI Document Review")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "https://ai-document-review-two-blond.vercel.app"
        ).split(",")
        if origin.strip()
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    # Size limit keeps us inside the free API tier.
    document_text: str = Field(max_length=50_000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/claims/extract", response_model=ClaimExtractionResult)
def claims_extract(request: ExtractRequest):
    try:
        return extract_claims(request.document_text)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error))


class RetrieveRequest(BaseModel):
    claims: list[Claim] = Field(max_length=50)  # the "claims" list from /claims/extract
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    source_text: str = Field(max_length=200_000)


@app.post("/evidence/retrieve", response_model=list[EvidenceResult])
def evidence_retrieve(request: RetrieveRequest):
    """Find candidate evidence for each claim in a plain text source. No LLM, no verdict."""
    source = load_text_source(request.source_id, request.source_text)
    return retrieve_for_claims(request.claims, source)


class VerifyRequest(BaseModel):
    claim: Claim
    evidence_chunks: list[EvidenceChunk] = Field(max_length=10)  # from /evidence/retrieve


@app.post("/claims/verify", response_model=VerificationResult)
def claims_verify(request: VerifyRequest):
    """Judge one claim; provider quota failures are reported instead of hidden as UNCLEAR."""
    try:
        return verify_claim(request.claim, request.evidence_chunks)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error))


class RiskRequest(BaseModel):
    document_text: str = Field(max_length=50_000)
    claims: list[Claim] = Field(default=[], max_length=100)
    verification_results: list[VerificationResult] = Field(default=[], max_length=100)


@app.post("/risk/analyze", response_model=RiskAnalysisResult)
def risk_analyze(request: RiskRequest):
    """Sensitive data + risky commitments + consequence + priority. No LLM, nothing is stored."""
    findings = build_findings(request.document_text, request.claims, request.verification_results)
    return RiskAnalysisResult(findings=findings, ranked_findings=rank_findings(findings),
                              total_findings=len(findings))


class AnalyzeRequest(BaseModel):
    document_text: str = Field(max_length=50_000)
    source_text: str = Field(max_length=200_000)
    source_id: str = Field(default="SRC1", pattern=SOURCE_ID_PATTERN)


@app.post("/analyze", response_model=PipelineResult)
def analyze(request: AnalyzeRequest):
    """Main entry point: the whole review pipeline. Nothing is stored or logged."""
    try:
        return review_document(request.document_text, request.source_text, request.source_id)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error))
