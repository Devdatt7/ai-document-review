from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["SUPPORTED", "CONTRADICTED", "NOT_FOUND"]
Status = Literal["READY", "REVIEW", "BLOCKED"]
Decision = Literal["accepted", "dismissed"]


class ClaimType(str, Enum):
    general = "general"
    financial = "financial"
    date = "date"
    entity = "entity"
    policy = "policy"
    legal = "legal"
    regulatory = "regulatory"
    commitment = "commitment"
    sensitive = "sensitive"
    other = "other"


class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: str = Field(pattern=r"^S\d+$")
    text: str = Field(min_length=1)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^C\d+$")
    sentence_id: str = Field(pattern=r"^S\d+$")
    claim_text: str = Field(min_length=1)
    claim_type: ClaimType


class ClaimExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentences: list[Sentence] = []
    claims: list[Claim] = []


# ---------- Retrieval: sources and evidence ----------

SOURCE_ID_PATTERN = r"^[A-Za-z0-9_]+$"  # no "-" because chunk IDs use "-" as a separator


class SourcePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: Optional[int] = Field(default=None, ge=1)  # None for plain text sources
    text: str


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    pages: list[SourcePage]


class EvidenceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    page: Optional[int] = None
    chunk_id: str  # e.g. SRC1-P1-C1
    text: str
    score: float = 0.0


class EvidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    evidence_chunks: list[EvidenceChunk] = []


# ---------- Verification ----------

class VerificationVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"        # evidence directly supports the claim
    CONTRADICTED = "CONTRADICTED"  # evidence directly conflicts with the claim
    UNSUPPORTED = "UNSUPPORTED"    # relevant evidence is absent or does not back the claim (NOT "false")
    UNCLEAR = "UNCLEAR"            # ambiguous, incomplete or unverifiable


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^C\d+$")
    verdict: VerificationVerdict
    explanation: str = Field(min_length=1)
    evidence_chunk_ids: list[str] = []
    evidence_quote: str = ""  # always a literal piece of a retrieved chunk, or empty
    confidence: float = Field(ge=0.0, le=1.0)


# ---------- Risk, consequence and priority ----------
# Four SEPARATE ideas: verdict (from verification), risk type (flag), consequence, priority.

class RiskType(str, Enum):
    SENSITIVE_DATA = "SENSITIVE_DATA"
    RISKY_COMMITMENT = "RISKY_COMMITMENT"


class ConsequenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(pattern=r"^F\d+$")
    claim_id: Optional[str] = None             # None for document-level sensitive-data findings
    verdict: Optional[VerificationVerdict] = None  # None if the claim was not verified
    risk_type: Optional[RiskType] = None       # None = no risk flag (e.g. just a contradicted claim)
    consequence: ConsequenceLevel
    priority_score: float = Field(ge=0.0, le=100.0)
    reason: str
    matched_text: Optional[str] = None         # risky phrase, or the MASKED value for sensitive data
    masked_text: Optional[str] = None          # sensitive data only: the line with values masked
    recommended_action: str


class RiskAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[RiskFinding]         # everything, in the order found
    ranked_findings: list[RiskFinding]  # same findings, most urgent first
    total_findings: int


# ---------- Document score, status and full pipeline result ----------

class DocumentStatus(str, Enum):
    READY = "READY"      # no currently detected issue needs human review (NOT "the document is true")
    REVIEW = "REVIEW"    # a person should look at some findings
    BLOCKED = "BLOCKED"  # at least one CRITICAL finding; do not send as-is


class DocumentScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_score: float = Field(ge=0.0, le=100.0)       # a review score, NOT a probability of truth
    evidence_coverage: float = Field(ge=0.0, le=100.0)  # % of claims with retrieved source evidence
    status: DocumentStatus
    summary: str
    finding_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    high_count: int = Field(ge=0)
    medium_count: int = Field(ge=0)
    low_count: int = Field(ge=0)


class PipelineResult(BaseModel):
    """Everything the reviewer needs: Claim -> Evidence -> Verdict -> Finding -> Priority."""
    model_config = ConfigDict(extra="forbid")

    sentences: list[Sentence]
    claims: list[Claim]
    evidence: list[EvidenceResult]               # one entry per claim (may be empty)
    verification_results: list[VerificationResult]
    findings: list[RiskFinding]                  # all findings, nothing hidden
    ranked_findings: list[RiskFinding]           # same findings, most urgent first
    score: DocumentScoreResult
    status: DocumentStatus                       # same as score.status, for convenience

class Evidence(BaseModel):
    source: str
    text: str
    score: float = 0.0


class ClaimResult(BaseModel):
    claim: Claim
    evidence: list[Evidence] = []
    verdict: Verdict = "NOT_FOUND"
    reason: str = ""
    flags: list[str] = []
    consequence: str = "low"
    priority: float = 0.0
    decision: Optional[Decision] = None


class DocumentResult(BaseModel):
    id: Optional[int] = None
    trust_score: float = 0.0
    status: Status = "REVIEW"
    claims: list[ClaimResult] = []
