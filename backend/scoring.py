"""Consequence, review priority, risk findings (and later: trust score and status).

Product policy, NOT real-world knowledge: the rules below are explicit choices we made so a
reviewer sees the riskiest items first. Nothing here is a learned probability.
"""

from checks import SensitiveMatch, find_pii, find_risky_phrases, masked_line
from models import (Claim, ClaimType, ConsequenceLevel, DocumentScoreResult, DocumentStatus,
                    EvidenceResult, RiskFinding, RiskType, VerificationResult, VerificationVerdict as V)

C = ConsequenceLevel


# ---------- Document trust score, evidence coverage, status ----------
#
# trust_score = 100 - sum of penalties, never below 0. One penalty per FINDING (a claim that is
# both contradicted and risky is already a single finding, so it is not counted twice):
#
#   CRITICAL -25 | HIGH -12 | MEDIUM -6 | LOW -2
#
# It is a review score under our policy. It is NOT the probability that the document is true.

PENALTY = {C.CRITICAL: 25, C.HIGH: 12, C.MEDIUM: 6, C.LOW: 2}


def calculate_trust_score(findings: list[RiskFinding]) -> float:
    return float(max(0, 100 - sum(PENALTY[f.consequence] for f in findings)))


def calculate_evidence_coverage(evidence: list[EvidenceResult], claim_count: int) -> float:
    """% of claims that had at least one retrieved chunk. Says nothing about whether claims are true."""
    if claim_count == 0:
        return 0.0
    covered = sum(1 for e in evidence if e.evidence_chunks)
    return round(100 * covered / claim_count, 1)


def decide_status(findings: list[RiskFinding], verifications: list[VerificationResult]) -> DocumentStatus:
    """Status policy:

    BLOCKED - any CRITICAL finding.
    REVIEW  - no critical finding, but any other finding, OR any claim that is UNSUPPORTED/UNCLEAR.
    READY   - none of the above. This means only "no detected issue needs human review under
              our configured policy". It does NOT mean the document is true.
    """
    if any(f.consequence == C.CRITICAL for f in findings):
        return DocumentStatus.BLOCKED
    if findings or any(v.verdict in (V.UNSUPPORTED, V.UNCLEAR) for v in verifications):
        return DocumentStatus.REVIEW
    return DocumentStatus.READY


def score_document(findings: list[RiskFinding], verifications: list[VerificationResult],
                   evidence: list[EvidenceResult], claim_count: int) -> DocumentScoreResult:
    """Combine findings, verdicts and evidence into one document-level result."""
    count = lambda level: sum(1 for f in findings if f.consequence == level)
    status = decide_status(findings, verifications)
    score = calculate_trust_score(findings)
    coverage = calculate_evidence_coverage(evidence, claim_count)
    return DocumentScoreResult(
        trust_score=score, evidence_coverage=coverage, status=status,
        summary=(f"{status.value}: {len(findings)} finding(s) for review. Trust score {score:.0f}/100 is a "
                 f"review score under our policy, not a probability that the document is true. "
                 f"Source evidence was found for {coverage:.0f}% of claims."),
        finding_count=len(findings), critical_count=count(C.CRITICAL), high_count=count(C.HIGH),
        medium_count=count(C.MEDIUM), low_count=count(C.LOW),
    )


# ---------- Consequence: "how harmful if this claim is wrong / this risk is missed?" ----------

CONSEQUENCE_RANK = {C.LOW: 1, C.MEDIUM: 2, C.HIGH: 3, C.CRITICAL: 4}

# claim_type -> (level, why). A risky phrase can only RAISE this level, never lower it.
TYPE_POLICY = {
    ClaimType.legal: (C.CRITICAL, "it makes a legal or contractual statement"),
    ClaimType.regulatory: (C.CRITICAL, "it makes a regulatory statement"),
    ClaimType.financial: (C.HIGH, "it states a financial amount"),
    ClaimType.date: (C.HIGH, "it states an important date or deadline"),
    ClaimType.entity: (C.HIGH, "it names a party"),
    ClaimType.commitment: (C.HIGH, "it states a business commitment"),
    ClaimType.sensitive: (C.HIGH, "it concerns sensitive information"),
    ClaimType.policy: (C.MEDIUM, "it describes an ordinary operational rule"),
    ClaimType.general: (C.LOW, "it is a general statement with limited practical impact"),
    ClaimType.other: (C.LOW, "it is a general statement with limited practical impact"),
}


def classify_consequence(claim_type: ClaimType, risky_phrases: list) -> tuple[ConsequenceLevel, str]:
    """Return (level, reason) for a claim. The reason always names the rule that was used."""
    level, why = TYPE_POLICY[claim_type]
    if risky_phrases and CONSEQUENCE_RANK[risky_phrases[0].consequence] > CONSEQUENCE_RANK[level]:
        level = risky_phrases[0].consequence
        why = "it creates a contractual guarantee or liability"
    elif risky_phrases and level == C.CRITICAL:
        why = "it creates a contractual guarantee or liability"
    return level, f"{level.value} because {why}."


# ---------- Priority: a 0-100 score from three explicit parts ----------
#
#   priority = consequence points + verdict points + risk-flag points      (max 40 + 30 + 30 = 100)
#
#   consequence:  LOW 10 | MEDIUM 20 | HIGH 30 | CRITICAL 40
#   verdict:      CONTRADICTED 30 | UNSUPPORTED 22 | UNCLEAR 12 | SUPPORTED 0 | not verified 0
#   risk flag:    SENSITIVE_DATA 30 | RISKY_COMMITMENT 25 | none 0
#
# Why: how bad a mistake would be matters most (up to 40); a verified problem adds up to 30;
# a risk flag is a problem on its own, so it adds up to 30 even if the claim is supported.
# Example: contradicted + HIGH = 60, sensitive CRITICAL = 70, contradicted risky CRITICAL = 95.

CONSEQUENCE_POINTS = {C.LOW: 10, C.MEDIUM: 20, C.HIGH: 30, C.CRITICAL: 40}
VERDICT_POINTS = {V.CONTRADICTED: 30, V.UNSUPPORTED: 22, V.UNCLEAR: 12, V.SUPPORTED: 0}
RISK_POINTS = {RiskType.SENSITIVE_DATA: 30, RiskType.RISKY_COMMITMENT: 25}


def calculate_priority(consequence: ConsequenceLevel, verdict: V | None, risk_type: RiskType | None) -> float:
    """Deterministic review priority, 0-100. Same inputs always give the same number."""
    points = CONSEQUENCE_POINTS[consequence]
    points += VERDICT_POINTS.get(verdict, 0) if verdict else 0
    points += RISK_POINTS[risk_type] if risk_type else 0
    return float(points)


# ---------- Findings ----------

VERDICT_REASON = {
    V.CONTRADICTED: "Claim is contradicted by supplied evidence.",
    V.UNSUPPORTED: "Supplied evidence does not support this claim (this does not prove it is false).",
    V.UNCLEAR: "Evidence is ambiguous or insufficient to decide.",
}


def _action(verdict: V | None, risk_type: RiskType | None) -> str:
    if risk_type == RiskType.SENSITIVE_DATA:
        return "Remove or redact this value before sharing the document."
    if verdict == V.CONTRADICTED:
        return "Correct the claim to match the source, or confirm the source is outdated."
    if risk_type == RiskType.RISKY_COMMITMENT:
        return "Have a person with authority confirm this commitment before it is sent."
    if verdict == V.UNSUPPORTED:
        return "Find a source for this claim or remove it."
    return "Check this claim against the source manually."


def claim_finding(claim: Claim, verification: VerificationResult | None, finding_id: str) -> RiskFinding | None:
    """One claim -> one finding, or None if there is nothing for a reviewer to look at.

    A SUPPORTED claim with no risky wording needs no review. Everything else does.
    """
    verdict = verification.verdict if verification else None
    phrases = find_risky_phrases(claim.claim_text)
    if verdict in (None, V.SUPPORTED) and not phrases:
        return None

    consequence, consequence_reason = classify_consequence(claim.claim_type, phrases)
    risk_type = RiskType.RISKY_COMMITMENT if phrases else None

    parts = [VERDICT_REASON.get(verdict, ""), phrases[0].reason if phrases else "", consequence_reason]
    return RiskFinding(
        finding_id=finding_id, claim_id=claim.claim_id, verdict=verdict, risk_type=risk_type,
        consequence=consequence, priority_score=calculate_priority(consequence, verdict, risk_type),
        reason=" ".join(p for p in parts if p),
        matched_text="; ".join(p.phrase for p in phrases) or None,
        recommended_action=_action(verdict, risk_type),
    )


def sensitive_finding(match: SensitiveMatch, text: str, matches: list[SensitiveMatch], finding_id: str) -> RiskFinding:
    """One sensitive value -> one finding. Only masked text is stored."""
    return RiskFinding(
        finding_id=finding_id, claim_id=None, verdict=None, risk_type=RiskType.SENSITIVE_DATA,
        consequence=match.consequence,
        priority_score=calculate_priority(match.consequence, None, RiskType.SENSITIVE_DATA),
        reason=(f"Potential personal identifier ({match.label}) appears in the AI-written document. "
                f"{match.consequence.value} because it could expose private or financial identity data."),
        matched_text=match.masked, masked_text=masked_line(text, match, matches),
        recommended_action=_action(None, RiskType.SENSITIVE_DATA),
    )


def build_findings(document_text: str, claims: list[Claim],
                   verifications: list[VerificationResult]) -> list[RiskFinding]:
    """Combine claims + verification results + sensitive data into findings (nothing is dropped)."""
    by_claim = {v.claim_id: v for v in verifications}
    findings: list[RiskFinding] = []
    matches = find_pii(document_text)

    for claim in claims:
        # The SENSITIVE_DATA finding below already reports this privacy issue, so a PII claim
        # (its text holds a sensitive value, or it is typed "sensitive") gets no second finding
        # for being UNSUPPORTED. Its verification result is still returned. Risky wording is
        # still flagged, and ordinary unsupported claims are unaffected.
        is_pii_claim = bool(matches) and (bool(find_pii(claim.claim_text))
                                          or claim.claim_type == ClaimType.sensitive)
        if is_pii_claim and not find_risky_phrases(claim.claim_text):
            continue
        finding = claim_finding(claim, by_claim.get(claim.claim_id), f"F{len(findings) + 1}")
        if finding:
            findings.append(finding)

    for match in matches:
        findings.append(sensitive_finding(match, document_text, matches, f"F{len(findings) + 1}"))
    return findings


# ---------- Ranking ----------

def rank_findings(findings: list[RiskFinding], k: int | None = None) -> list[RiskFinding]:
    """Most urgent first. Ties: higher consequence, then lower finding number (always stable).

    k only limits what is returned here; the full list is never modified.
    """
    ranked = sorted(findings, key=lambda f: (-f.priority_score, -CONSEQUENCE_RANK[f.consequence],
                                             int(f.finding_id[1:])))
    return ranked if k is None else ranked[:k]
