import { FLAWED_PRESET } from "./demo.js";
import { FLAWED_SAMPLE_REPORT } from "./sampleReports.js";

export const ORIGINAL_REIMBURSEMENT_PASSAGE =
  "Reimbursement is capped at ₹25,000 per claim and is paid within 10 working days.";
export const UPDATED_REIMBURSEMENT_PASSAGE =
  "Reimbursement is capped at ₹50,000 per claim and is paid within 10 working days.";

const REIMBURSEMENT_CLAIM_ID = "C1";
const REIMBURSEMENT_CHUNK_ID = "SRC1-P1-C3";
const FINDING_PENALTIES = { CRITICAL: 25, HIGH: 12, MEDIUM: 6, LOW: 2 };

export const UPDATED_FLAWED_SOURCE = FLAWED_PRESET.source.replace(
  ORIGINAL_REIMBURSEMENT_PASSAGE,
  UPDATED_REIMBURSEMENT_PASSAGE,
);

function recomputeScore(findings, verifications, evidence, claimCount) {
  const trustScore = Math.max(
    0,
    100 - findings.reduce((total, item) => total + FINDING_PENALTIES[item.consequence], 0),
  );
  const evidenceCoverage = claimCount === 0
    ? 0
    : Math.round((100 * evidence.filter((item) => item.evidence_chunks.length > 0).length / claimCount) * 10) / 10;
  const status = findings.some((item) => item.consequence === "CRITICAL")
    ? "BLOCKED"
    : findings.length > 0
      || verifications.some((item) => ["UNSUPPORTED", "UNCLEAR"].includes(item.verdict))
      ? "REVIEW"
      : "READY";
  const counts = Object.fromEntries(
    ["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((level) => [
      `${level.toLowerCase()}_count`,
      findings.filter((item) => item.consequence === level).length,
    ]),
  );

  return {
    ...FLAWED_SAMPLE_REPORT.score,
    trust_score: trustScore,
    evidence_coverage: evidenceCoverage,
    status,
    summary: `${status}: ${findings.length} finding(s) for review. Trust score ${trustScore}/100 is a review score under our policy, not a probability that the document is true. Source evidence was found for ${evidenceCoverage}% of claims.`,
    finding_count: findings.length,
    ...counts,
  };
}

export function createSourceChangeDemo() {
  if (!FLAWED_PRESET.source.includes(ORIGINAL_REIMBURSEMENT_PASSAGE)) {
    throw new Error("The prepared source-change scenario no longer matches the flawed sample source.");
  }
  const originalVerification = FLAWED_SAMPLE_REPORT.verification_results.find(
    (item) => item.claim_id === REIMBURSEMENT_CLAIM_ID,
  );
  if (originalVerification?.verdict !== "CONTRADICTED"
      || !FLAWED_SAMPLE_REPORT.findings.some((item) => item.claim_id === REIMBURSEMENT_CLAIM_ID)) {
    throw new Error("The reimbursement claim no longer matches the prepared contradicted sample scenario.");
  }

  const evidence = FLAWED_SAMPLE_REPORT.evidence.map((entry) => {
    if (entry.claim_id !== REIMBURSEMENT_CLAIM_ID) return entry;
    const chunkFound = entry.evidence_chunks.some((item) => item.chunk_id === REIMBURSEMENT_CHUNK_ID);
    if (!chunkFound) {
      throw new Error("The reimbursement sample evidence chunk was not found.");
    }
    return {
      ...entry,
      evidence_chunks: entry.evidence_chunks.map((item) => item.chunk_id === REIMBURSEMENT_CHUNK_ID
        ? { ...item, text: UPDATED_REIMBURSEMENT_PASSAGE }
        : item),
    };
  });
  if (!evidence.some((entry) => entry.claim_id === REIMBURSEMENT_CLAIM_ID)) {
    throw new Error("The reimbursement sample evidence was not found.");
  }

  const verificationResults = FLAWED_SAMPLE_REPORT.verification_results.map((item) => (
    item.claim_id === REIMBURSEMENT_CLAIM_ID
      ? {
        ...item,
        verdict: "SUPPORTED",
        explanation: "The updated sample source states the same ₹50,000 reimbursement cap as the claim.",
        evidence_quote: UPDATED_REIMBURSEMENT_PASSAGE,
      }
      : item
  ));
  if (!verificationResults.some((item) => item.claim_id === REIMBURSEMENT_CLAIM_ID
      && item.verdict === "SUPPORTED")) {
    throw new Error("The reimbursement sample verification was not found.");
  }

  const findings = FLAWED_SAMPLE_REPORT.findings.filter(
    (item) => item.claim_id !== REIMBURSEMENT_CLAIM_ID,
  );
  const rankedFindings = FLAWED_SAMPLE_REPORT.ranked_findings.filter(
    (item) => item.claim_id !== REIMBURSEMENT_CLAIM_ID,
  );
  const score = recomputeScore(
    findings,
    verificationResults,
    evidence,
    FLAWED_SAMPLE_REPORT.claims.length,
  );
  const report = {
    ...FLAWED_SAMPLE_REPORT,
    evidence,
    verification_results: verificationResults,
    findings,
    ranked_findings: rankedFindings,
    score,
    status: score.status,
  };

  return { report, sourceText: UPDATED_FLAWED_SOURCE };
}

export function resetSourceChangeDemo() {
  return { report: FLAWED_SAMPLE_REPORT, sourceText: FLAWED_PRESET.source };
}
