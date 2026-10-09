// Prebuilt PipelineResult-shaped reports for offline demonstrations. These are not analyses.
const sentence = (sentence_id, text) => ({ sentence_id, text });
const claim = (claim_id, sentence_id, claim_text, claim_type) => ({
  claim_id, sentence_id, claim_text, claim_type,
});
const chunk = (chunk_id, text, score = 0) => ({
  source_id: "SRC1", page: null, chunk_id, text, score,
});
const evidence = (claim_id, chunks = []) => ({ claim_id, evidence_chunks: chunks });
const verification = (claim_id, verdict, explanation, evidence_chunk_ids = [], evidence_quote = "", confidence = 0) => ({
  claim_id, verdict, explanation, evidence_chunk_ids, evidence_quote, confidence,
});
const finding = (finding_id, claim_id, verdict, risk_type, consequence, priority_score, reason,
  matched_text, masked_text, recommended_action) => ({
  finding_id, claim_id, verdict, risk_type, consequence, priority_score, reason,
  matched_text, masked_text, recommended_action,
});

const refundChunkText = "Refunds are available within 30 days of purchase. Customized products are not eligible for a refund.";
const reimbursementChunkText = "Reimbursement is capped at ₹25,000 per claim and is paid within 10 working days.";
const effectiveDateChunkText = "This policy is effective from 1 January 2026.";
const availabilityChunkText = "Service availability is targeted at 99.5% per month. This is a target, not a guarantee.";
const parkingChunkText = "Parking is available for visitors on the ground floor at a daily charge.";

export const GOOD_SAMPLE_REPORT = {
  sentences: [
    sentence("S1", "Refunds are available within 30 days of purchase."),
    sentence("S2", "Customized products are not eligible for a refund."),
    sentence("S3", "Reimbursement is capped at ₹25,000 per claim."),
    sentence("S4", "Reimbursement is paid within 10 working days."),
    sentence("S5", "This policy is effective from 1 January 2026."),
    sentence("S6", "Monthly service availability is targeted at 99.5%."),
    sentence("S7", "Parking is available for visitors on the ground floor at a daily charge."),
  ],
  claims: [
    claim("C1", "S1", "Refunds are available within 30 days of purchase.", "policy"),
    claim("C2", "S2", "Customized products are not eligible for a refund.", "policy"),
    claim("C3", "S3", "Reimbursement is capped at ₹25,000 per claim.", "financial"),
    claim("C4", "S4", "Reimbursement is paid within 10 working days.", "policy"),
    claim("C5", "S5", "This policy is effective from 1 January 2026.", "date"),
    claim("C6", "S6", "Monthly service availability is targeted at 99.5%.", "policy"),
    claim("C7", "S7", "Parking is available for visitors on the ground floor at a daily charge.", "policy"),
  ],
  evidence: [
    evidence("C1", [chunk("SRC1-P1-C2", refundChunkText)]),
    evidence("C2", [chunk("SRC1-P1-C2", refundChunkText)]),
    evidence("C3", [chunk("SRC1-P1-C3", reimbursementChunkText)]),
    evidence("C4", [chunk("SRC1-P1-C3", reimbursementChunkText)]),
    evidence("C5", [chunk("SRC1-P1-C4", effectiveDateChunkText)]),
    evidence("C6", [chunk("SRC1-P1-C5", availabilityChunkText)]),
    evidence("C7", [chunk("SRC1-P1-C6", parkingChunkText)]),
  ],
  verification_results: [
    verification("C1", "SUPPORTED", "The source confirms the 30-day refund window.",
      ["SRC1-P1-C2"], "Refunds are available within 30 days of purchase."),
    verification("C2", "SUPPORTED", "The source states that customized products are not eligible for a refund.",
      ["SRC1-P1-C2"], "Customized products are not eligible for a refund."),
    verification("C3", "SUPPORTED", "The source states the reimbursement cap.",
      ["SRC1-P1-C3"], "Reimbursement is capped at ₹25,000 per claim"),
    verification("C4", "SUPPORTED", "The source states the payment term.",
      ["SRC1-P1-C3"], "paid within 10 working days"),
    verification("C5", "SUPPORTED", "The source confirms the policy effective date.",
      ["SRC1-P1-C4"], "This policy is effective from 1 January 2026."),
    verification("C6", "SUPPORTED", "The source describes 99.5% as a monthly availability target.",
      ["SRC1-P1-C5"], "Service availability is targeted at 99.5% per month."),
    verification("C7", "SUPPORTED", "The source states that visitor parking has a daily charge.",
      ["SRC1-P1-C6"], "Parking is available for visitors on the ground floor at a daily charge."),
  ],
  findings: [],
  ranked_findings: [],
  score: {
    trust_score: 100,
    evidence_coverage: 100,
    status: "READY",
    summary: "READY: 0 finding(s) for review. Trust score 100/100 is a review score under our policy, not a probability that the document is true. Source evidence was found for 100% of claims.",
    finding_count: 0,
    critical_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
  },
  status: "READY",
};

const flawedSentences = [
  sentence("S1", "The maximum reimbursement is ₹50,000."),
  sentence("S2", "The policy is effective from 1 April 2026."),
  sentence("S3", "The service guarantees 100% uptime."),
  sentence("S4", "The office has free parking."),
  sentence("S5", "Premium roadside assistance is included with every purchase."),
  sentence("S6", "Customer PAN: AB*****34F."),
];

const flawedClaims = [
  claim("C1", "S1", "The maximum reimbursement is ₹50,000.", "financial"),
  claim("C2", "S2", "The policy is effective from 1 April 2026.", "date"),
  claim("C3", "S3", "The service guarantees 100% uptime.", "commitment"),
  claim("C4", "S4", "The office has free parking.", "policy"),
  claim("C5", "S5", "Premium roadside assistance is included with every purchase.", "general"),
];

const flawedFindings = [
  finding(
    "F1", "C1", "CONTRADICTED", null, "HIGH", 60,
    "Claim is contradicted by supplied evidence. HIGH because it states a financial amount.",
    null, null, "Correct the claim to match the source, or confirm the source is outdated.",
  ),
  finding(
    "F2", "C2", "CONTRADICTED", null, "HIGH", 60,
    "Claim is contradicted by supplied evidence. HIGH because it states an important date or deadline.",
    null, null, "Correct the claim to match the source, or confirm the source is outdated.",
  ),
  finding(
    "F3", "C3", "CONTRADICTED", "RISKY_COMMITMENT", "CRITICAL", 95,
    "Claim is contradicted by supplied evidence. Claim makes an explicit guarantee. CRITICAL because it creates a contractual guarantee or liability.",
    "guarantees; 100% uptime", null,
    "Correct the claim to match the source, or confirm the source is outdated.",
  ),
  finding(
    "F4", "C4", "CONTRADICTED", null, "MEDIUM", 50,
    "Claim is contradicted by supplied evidence. MEDIUM because it describes an ordinary operational rule.",
    null, null, "Correct the claim to match the source, or confirm the source is outdated.",
  ),
  finding(
    "F5", "C5", "UNSUPPORTED", null, "LOW", 32,
    "Supplied evidence does not support this claim (this does not prove it is false). LOW because it is a general statement with limited practical impact.",
    null, null, "Find a source for this claim or remove it.",
  ),
  finding(
    "F6", null, null, "SENSITIVE_DATA", "CRITICAL", 70,
    "Potential personal identifier (PAN (Indian tax ID)) appears in the AI-written document. CRITICAL because it could expose private or financial identity data.",
    "AB*****34F", "Customer PAN: AB*****34F.",
    "Remove or redact this value before sharing the document.",
  ),
];

export const FLAWED_SAMPLE_REPORT = {
  sentences: flawedSentences,
  claims: flawedClaims,
  evidence: [
    evidence("C1", [chunk("SRC1-P1-C3", reimbursementChunkText)]),
    evidence("C2", [chunk("SRC1-P1-C4", effectiveDateChunkText)]),
    evidence("C3", [chunk("SRC1-P1-C5", availabilityChunkText)]),
    evidence("C4", [chunk("SRC1-P1-C6", parkingChunkText)]),
    evidence("C5", [chunk("SRC1-P1-C2", refundChunkText)]),
  ],
  verification_results: [
    verification("C1", "CONTRADICTED", "The document gives a different cap from the source.",
      ["SRC1-P1-C3"], "Reimbursement is capped at ₹25,000 per claim"),
    verification("C2", "CONTRADICTED", "The document gives a different effective date from the source.",
      ["SRC1-P1-C4"], "This policy is effective from 1 January 2026."),
    verification("C3", "CONTRADICTED", "The source says availability is a target and expressly distinguishes it from a guarantee.",
      ["SRC1-P1-C5"], "Service availability is targeted at 99.5% per month. This is a target, not a guarantee."),
    verification("C4", "CONTRADICTED", "The source says visitor parking has a daily charge.",
      ["SRC1-P1-C6"], "Parking is available for visitors on the ground floor at a daily charge."),
    verification("C5", "UNSUPPORTED", "The retrieved source passage does not mention roadside assistance and does not substantiate this claim.",
      [], ""),
  ],
  findings: flawedFindings,
  ranked_findings: [
    flawedFindings[2], flawedFindings[5], flawedFindings[0],
    flawedFindings[1], flawedFindings[3], flawedFindings[4],
  ],
  score: {
    trust_score: 18,
    evidence_coverage: 100,
    status: "BLOCKED",
    summary: "BLOCKED: 6 finding(s) for review. Trust score 18/100 is a review score under our policy, not a probability that the document is true. Source evidence was found for 100% of claims.",
    finding_count: 6,
    critical_count: 2,
    high_count: 2,
    medium_count: 1,
    low_count: 1,
  },
  status: "BLOCKED",
};
