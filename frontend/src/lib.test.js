// Run with: npm test   (Node's built-in test runner, no extra packages)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { buildFindingViews, describeHttpError, priorityBreakdown, sentenceSeverity, splitByReview } from "./lib.js";
import { DEMO_SOURCE, FLAWED_DOCUMENT, GOOD_DOCUMENT } from "./demo.js";
import { FLAWED_SAMPLE_REPORT, GOOD_SAMPLE_REPORT } from "./sampleReports.js";

const result = {
  sentences: [
    { sentence_id: "S1", text: "The maximum reimbursement is ₹50,000." },
    { sentence_id: "S2", text: "Customer PAN: AB*****34F." },
  ],
  claims: [{ claim_id: "C1", sentence_id: "S1", claim_text: "The maximum reimbursement is ₹50,000.", claim_type: "financial" }],
  evidence: [{ claim_id: "C1", evidence_chunks: [
    { source_id: "SRC1", page: null, chunk_id: "SRC1-P1-C2", text: "Reimbursement is capped at ₹25,000 per claim.", score: 1 }] }],
  verification_results: [{ claim_id: "C1", verdict: "CONTRADICTED", explanation: "x",
    evidence_chunk_ids: ["SRC1-P1-C2"], evidence_quote: "Reimbursement is capped at ₹25,000 per claim.", confidence: 0.9 }],
  ranked_findings: [
    { finding_id: "F2", claim_id: null, verdict: null, risk_type: "SENSITIVE_DATA", consequence: "CRITICAL",
      priority_score: 70, reason: "pii", matched_text: "AB*****34F", masked_text: "Customer PAN: AB*****34F.", recommended_action: "Redact" },
    { finding_id: "F1", claim_id: "C1", verdict: "CONTRADICTED", risk_type: null, consequence: "HIGH",
      priority_score: 60, reason: "r", matched_text: null, masked_text: null, recommended_action: "Fix" },
  ],
};

test("keeps backend ranked order and links claim, sentence and evidence", () => {
  const views = buildFindingViews(result);
  assert.deepEqual(views.map((v) => v.finding.finding_id), ["F2", "F1"]);
  assert.equal(views[1].sentenceId, "S1");
  assert.equal(views[1].sentence.text, "The maximum reimbursement is ₹50,000.");
  assert.equal(views[1].evidenceChunks[0].chunk_id, "SRC1-P1-C2");
  assert.match(views[1].evidenceQuote, /25,000/);
});

test("PII finding maps to its masked sentence and never shows a raw value", () => {
  const view = buildFindingViews(result)[0];
  assert.equal(view.sentenceId, "S2");
  assert.equal(view.evidenceQuote, null);
  assert.ok(!JSON.stringify(view).includes("ABCDE1234F"));
});

test("dismiss moves a finding out of the open list without changing the result", () => {
  const views = buildFindingViews(result);
  const { open, dismissed } = splitByReview(views, { F2: "dismissed" });
  assert.deepEqual(open.map((v) => v.finding.finding_id), ["F1"]);
  assert.deepEqual(dismissed.map((v) => v.finding.finding_id), ["F2"]);
  assert.equal(result.ranked_findings.length, 2);
});

test("restore and accept both keep the finding open", () => {
  const views = buildFindingViews(result);
  assert.equal(splitByReview(views, {}).open.length, 2);
  assert.equal(splitByReview(views, { F1: "accepted" }).open.length, 2);
});

test("priority breakdown uses the existing consequence, verdict and risk points", () => {
  assert.deepEqual(priorityBreakdown(result.ranked_findings[0]), [
    { label: "CRITICAL consequence", points: 40 },
    { label: "No verification verdict", points: 0 },
    { label: "SENSITIVE DATA", points: 30 },
  ]);
  assert.deepEqual(priorityBreakdown(result.ranked_findings[1]), [
    { label: "HIGH consequence", points: 30 },
    { label: "CONTRADICTED", points: 30 },
    { label: "No risk flag", points: 0 },
  ]);
});

test("highlight uses the most severe open finding per sentence", () => {
  const views = buildFindingViews(result);
  assert.deepEqual(sentenceSeverity(views), { S2: "CRITICAL", S1: "HIGH" });
  assert.deepEqual(sentenceSeverity(splitByReview(views, { F2: "dismissed" }).open), { S1: "HIGH" });
});

test("http errors become readable messages", () => {
  assert.match(describeHttpError(502, "GEMINI_API_KEY is not set"), /no verification was done/);
  assert.match(
    describeHttpError(502, "Gemini's rate or usage limit was reached. Check your quota and retry after reset."),
    /rate or usage limit was reached.*retry after reset/,
  );
  assert.match(describeHttpError(422, []), /rejected/);
  assert.match(describeHttpError(500, ""), /Server error \(500\)/);
});

const sampleFile = (relativePath) => readFileSync(
  fileURLToPath(new URL(relativePath, import.meta.url)),
  "utf8",
).replaceAll("\r\n", "\n").trimEnd();

test("offline presets match the committed synthetic documents and trusted source", () => {
  assert.equal(GOOD_DOCUMENT, sampleFile("../../data/samples/claim_good_demo.txt"));
  assert.equal(FLAWED_DOCUMENT, sampleFile("../../data/samples/claim_flawed_demo.txt"));
  assert.equal(DEMO_SOURCE, sampleFile("../../data/sources/refund_policy.txt"));
});

function assertPipelineReport(report, { expectedScore, expectedCoverage, expectedStatus }) {
  assert.deepEqual(Object.keys(report).sort(), [
    "claims", "evidence", "findings", "ranked_findings", "score", "sentences", "status",
    "verification_results",
  ]);
  assert.equal(report.status, report.score.status);
  assert.equal(report.score.trust_score, expectedScore);
  assert.equal(report.score.evidence_coverage, expectedCoverage);
  assert.equal(report.status, expectedStatus);
  assert.equal(report.score.finding_count, report.findings.length);

  const sentences = new Map(report.sentences.map((item) => [item.sentence_id, item]));
  const verifications = new Map(report.verification_results.map((item) => [item.claim_id, item]));
  const evidenceByClaim = new Map(report.evidence.map((item) => [item.claim_id, item.evidence_chunks]));
  const claims = new Map(report.claims.map((item) => [item.claim_id, item]));
  assert.equal(report.evidence.length, report.claims.length);
  assert.equal(report.verification_results.length, report.claims.length);

  for (const claim of report.claims) {
    assert.match(claim.claim_id, /^C\d+$/);
    assert.match(claim.sentence_id, /^S\d+$/);
    assert.ok(sentences.has(claim.sentence_id));
    assert.ok(verifications.has(claim.claim_id));
    const claimChunks = new Map((evidenceByClaim.get(claim.claim_id) || [])
      .map((item) => [item.chunk_id, item]));
    const result = verifications.get(claim.claim_id);
    for (const chunkId of result.evidence_chunk_ids) assert.ok(claimChunks.has(chunkId));
    if (result.evidence_quote) {
      assert.ok(result.evidence_chunk_ids.some((id) => claimChunks.get(id).text.includes(result.evidence_quote)));
    }
  }

  const expectedPriorities = { CRITICAL: 40, HIGH: 30, MEDIUM: 20, LOW: 10 };
  const verdictPoints = { CONTRADICTED: 30, UNSUPPORTED: 22, UNCLEAR: 12, SUPPORTED: 0 };
  const riskPoints = { SENSITIVE_DATA: 30, RISKY_COMMITMENT: 25 };
  const penalties = { CRITICAL: 25, HIGH: 12, MEDIUM: 6, LOW: 2 };
  let penaltyTotal = 0;
  const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  for (const finding of report.findings) {
    assert.match(finding.finding_id, /^F\d+$/);
    if (finding.claim_id) assert.ok(claims.has(finding.claim_id));
    const calculatedPriority = expectedPriorities[finding.consequence]
      + (verdictPoints[finding.verdict] || 0)
      + (riskPoints[finding.risk_type] || 0);
    assert.equal(finding.priority_score, calculatedPriority);
    penaltyTotal += penalties[finding.consequence];
    counts[finding.consequence] += 1;
  }
  assert.equal(report.score.trust_score, Math.max(0, 100 - penaltyTotal));
  assert.deepEqual(
    report.ranked_findings.map((item) => item.finding_id),
    [...report.findings].sort((a, b) => b.priority_score - a.priority_score
      || expectedPriorities[b.consequence] - expectedPriorities[a.consequence]
      || Number(a.finding_id.slice(1)) - Number(b.finding_id.slice(1)))
      .map((item) => item.finding_id),
  );
  for (const level of Object.keys(counts)) {
    assert.equal(report.score[`${level.toLowerCase()}_count`], counts[level]);
  }
  const supportedFindings = report.findings.filter((item) => item.verdict === "SUPPORTED");
  assert.equal(supportedFindings.length, 0);
}

test("good offline report contains only supported claims and no artificial findings", () => {
  assertPipelineReport(GOOD_SAMPLE_REPORT, {
    expectedScore: 100,
    expectedCoverage: 100,
    expectedStatus: "READY",
  });
  assert.ok(GOOD_SAMPLE_REPORT.verification_results.every((item) => item.verdict === "SUPPORTED"));
  assert.deepEqual(buildFindingViews(GOOD_SAMPLE_REPORT), []);
});

test("flawed offline report uses exact source quotes, masked PAN and policy-consistent scoring", () => {
  assertPipelineReport(FLAWED_SAMPLE_REPORT, {
    expectedScore: 18,
    expectedCoverage: 100,
    expectedStatus: "BLOCKED",
  });
  const reportText = JSON.stringify(FLAWED_SAMPLE_REPORT);
  assert.ok(!reportText.includes("ABCDE1234F"));
  assert.ok(reportText.includes("AB*****34F"));
  assert.equal(FLAWED_SAMPLE_REPORT.verification_results.find((item) => item.claim_id === "C5").verdict,
    "UNSUPPORTED");
  assert.equal(FLAWED_SAMPLE_REPORT.evidence.find((item) => item.claim_id === "C5").evidence_chunks[0].chunk_id,
    "SRC1-P1-C2");
  assert.deepEqual(FLAWED_SAMPLE_REPORT.ranked_findings.map((item) => item.finding_id),
    ["F3", "F6", "F1", "F2", "F4", "F5"]);
  assert.equal(buildFindingViews(FLAWED_SAMPLE_REPORT).length, 6);
});
