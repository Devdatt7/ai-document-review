// Small helpers that only RESHAPE the /analyze response for display.
// No scoring, status or verdict logic lives here: the backend is the source of truth.

export const CONSEQUENCE_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const INPUT_CHANGE_NOTICE =
  "The report was cleared because an input changed. Load a sample report or analyze again.";

export function assessmentAfterInputChange(hasAssessment) {
  return {
    result: null,
    resultMode: null,
    decisions: {},
    selectedId: null,
    notice: hasAssessment ? INPUT_CHANGE_NOTICE : "",
  };
}

const CONSEQUENCE_POINTS = { LOW: 10, MEDIUM: 20, HIGH: 30, CRITICAL: 40 };
const VERDICT_POINTS = { CONTRADICTED: 30, UNSUPPORTED: 22, UNCLEAR: 12, SUPPORTED: 0 };
const RISK_POINTS = { SENSITIVE_DATA: 30, RISKY_COMMITMENT: 25 };

// Explain the backend's established priority formula without changing its score or ordering.
export function priorityBreakdown(finding) {
  return [
    { label: `${finding.consequence} consequence`, points: CONSEQUENCE_POINTS[finding.consequence] ?? 0 },
    { label: finding.verdict || "No verification verdict", points: VERDICT_POINTS[finding.verdict] ?? 0 },
    { label: finding.risk_type?.replaceAll("_", " ") || "No risk flag", points: RISK_POINTS[finding.risk_type] ?? 0 },
  ];
}

// Pair each finding with the claim, sentence and evidence the backend already returned.
// Findings keep the backend's ranked order.
export function buildFindingViews(result) {
  const claims = new Map((result.claims || []).map((c) => [c.claim_id, c]));
  const verifications = new Map((result.verification_results || []).map((v) => [v.claim_id, v]));
  const chunks = new Map();
  for (const e of result.evidence || []) {
    for (const c of e.evidence_chunks || []) chunks.set(c.chunk_id, c);
  }
  const sentences = result.sentences || [];

  return (result.ranked_findings || []).map((finding) => {
    const claim = finding.claim_id ? claims.get(finding.claim_id) : null;
    const verification = finding.claim_id ? verifications.get(finding.claim_id) : null;
    const sentenceId = claim ? claim.sentence_id : findSentenceForMatch(sentences, finding);
    const sentence = sentences.find((s) => s.sentence_id === sentenceId) || null;
    const evidenceChunks = (verification?.evidence_chunk_ids || [])
      .map((id) => chunks.get(id))
      .filter(Boolean);
    return {
      finding,
      claim,
      sentence,
      verification,
      sentenceId: sentenceId || null,
      // Document-level findings (PII) have no claim; show the masked text the backend returned.
      affectedText: claim ? claim.claim_text : sentence ? sentence.text : finding.masked_text || "",
      evidenceQuote: verification?.evidence_quote || null,
      evidenceChunks,
    };
  });
}

// PII findings have no claim_id, so find the (already masked) sentence that contains the masked value.
function findSentenceForMatch(sentences, finding) {
  if (!finding.matched_text) return null;
  const hit = sentences.find((s) => s.text.includes(finding.matched_text));
  return hit ? hit.sentence_id : null;
}

// Reviewer decisions are kept separately from the backend result: { [finding_id]: "accepted" | "dismissed" }.
export function splitByReview(views, decisions) {
  const open = [];
  const dismissed = [];
  for (const v of views) {
    (decisions[v.finding.finding_id] === "dismissed" ? dismissed : open).push(v);
  }
  return { open, dismissed };
}

// Most severe open finding per sentence, used only to colour the highlight.
export function sentenceSeverity(openViews) {
  const out = {};
  for (const v of openViews) {
    if (!v.sentenceId) continue;
    const current = out[v.sentenceId];
    const level = v.finding.consequence;
    if (!current || CONSEQUENCE_ORDER.indexOf(level) < CONSEQUENCE_ORDER.indexOf(current)) {
      out[v.sentenceId] = level;
    }
  }
  return out;
}

// Turn a failed fetch / HTTP error into a message a reviewer can act on.
export function describeHttpError(status, detail) {
  const text = typeof detail === "string" ? detail : Array.isArray(detail) ? "The request was not valid." : "";
  if (status === 422) return `The input was rejected (too long or invalid). ${text}`.trim();
  if (status >= 400 && status < 500) return `Request error (${status}). ${text}`.trim();
  if (status === 502) return `The AI service failed, so no verification was done. ${text}`.trim();
  return `Server error (${status}). ${text}`.trim();
}
