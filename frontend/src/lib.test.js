// Run with: npm test   (Node's built-in test runner, no extra packages)
import assert from "node:assert/strict";
import test from "node:test";
import { buildFindingViews, describeHttpError, priorityBreakdown, sentenceSeverity, splitByReview } from "./lib.js";

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
  assert.match(describeHttpError(422, []), /rejected/);
  assert.match(describeHttpError(500, ""), /Server error \(500\)/);
});
