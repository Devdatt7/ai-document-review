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

export const PRIORITY_BANDS = [
  { id: "highest", label: "Highest priority", range: "80–100", min: 80 },
  { id: "high", label: "High priority", range: "60–79", min: 60 },
  { id: "medium", label: "Medium priority", range: "40–59", min: 40 },
  { id: "lower", label: "Lower priority", range: "0–39", min: 0 },
];

export function priorityBand(score) {
  if (score >= 80) return "highest";
  if (score >= 60) return "high";
  if (score >= 40) return "medium";
  return "lower";
}

export function groupByPriority(views) {
  return PRIORITY_BANDS.map((band) => ({
    ...band,
    findings: views.filter((view) => priorityBand(view.finding.priority_score) === band.id),
  }));
}

export function priorityBreakdownSegments(finding) {
  const segments = priorityBreakdown(finding);
  const keys = ["consequence", "verdict", "risk"];
  const labels = ["Consequence points", "Verdict points", "Risk-flag points"];
  return segments.map((segment, index) => ({
    key: keys[index],
    label: labels[index],
    points: segment.points,
    width: segment.points,
  }));
}

export function priorityExplanation(finding) {
  const [consequence, verdict, risk] = priorityBreakdown(finding);
  const riskText = finding.risk_type
    ? `${risk.points} from the ${risk.label.toLowerCase()} flag`
    : "no points from a risk flag";
  const verdictText = finding.verdict
    ? `${verdict.points} from the ${finding.verdict.toLowerCase()} verdict`
    : "no points from a verification verdict";
  return `Priority ${Math.round(finding.priority_score)}/100: ${consequence.points} for ${finding.consequence.toLowerCase()} consequence, ${verdictText}, and ${riskText}. These are review-priority heuristics.`;
}

export function priorityProgress(views, decisions) {
  const totalPoints = views.reduce(
    (total, view) => total + Math.max(0, Number(view.finding.priority_score) || 0),
    0,
  );
  const reviewed = views.filter((view) => Boolean(decisions[view.finding.finding_id]));
  const pointsReviewed = reviewed.reduce(
    (total, view) => total + Math.max(0, Number(view.finding.priority_score) || 0),
    0,
  );
  return {
    reviewedCount: reviewed.length,
    totalCount: views.length,
    pointsReviewed,
    totalPoints,
    percentage: totalPoints > 0 ? Math.round((pointsReviewed / totalPoints) * 100) : 0,
  };
}

export function reviewDecisionTransition(views, decisions, findingId, decision) {
  const nextDecisions = { ...decisions };
  if (decision) nextDecisions[findingId] = decision;
  else delete nextDecisions[findingId];

  const currentIndex = views.findIndex((view) => view.finding.finding_id === findingId);
  let selectedId = findingId;
  if (decision === "accepted" || decision === "dismissed") {
    const orderedViews = currentIndex < 0
      ? views
      : [...views.slice(currentIndex + 1), ...views.slice(0, currentIndex)];
    const nextUnreviewed = orderedViews.find(
      (view) => !nextDecisions[view.finding.finding_id],
    );
    if (nextUnreviewed) selectedId = nextUnreviewed.finding.finding_id;
  }

  return { decisions: nextDecisions, selectedId };
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
