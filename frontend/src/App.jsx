import { useEffect, useMemo, useRef, useState } from "react";
import { analyzeDocument } from "./api.js";
import { FLAWED_PRESET, GOOD_PRESET } from "./demo.js";
import {
  assessmentAfterInputChange,
  buildFindingViews,
  priorityBreakdown,
  sentenceSeverity,
  splitByReview,
} from "./lib.js";
import { FLAWED_SAMPLE_REPORT, GOOD_SAMPLE_REPORT } from "./sampleReports.js";
import {
  createSourceChangeDemo,
  resetSourceChangeDemo,
  UPDATED_REIMBURSEMENT_PASSAGE,
} from "./sourceChangeDemo.js";
import "./styles.css";

function readTextFile(file, onLoad, onError) {
  const reader = new FileReader();
  reader.onload = () => onLoad(String(reader.result || ""));
  reader.onerror = onError;
  reader.readAsText(file);
}

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M6 3.75h8l4 4v12.5H6z" />
        <path d="M14 3.75v4h4M9 12h6M9 15.5h3" />
        <path d="m14.5 16 1.5 1.5 3-3" />
      </svg>
    </span>
  );
}

function SampleCard({ tone, title, description, detail, onClick }) {
  return (
    <article className={`sample-card ${tone}`}>
      <span className="sample-card-icon" aria-hidden="true">
        {tone === "good" ? "✓" : "!"}
      </span>
      <div className="sample-card-copy">
        <h3>{title}</h3>
        <p>{description}</p>
        <span className="sample-card-detail">{detail}</span>
      </div>
      <button type="button" className="sample-card-action" onClick={onClick}>
        Explore report <span aria-hidden="true">→</span>
      </button>
    </article>
  );
}

function SourceChangeRecheck({ report, simulated, onSimulate, onReset }) {
  const previousScore = FLAWED_SAMPLE_REPORT.score;
  const currentScore = report.score;
  const currentVerification = report.verification_results.find((item) => item.claim_id === "C1");

  return (
    <section className={`source-change-demo ${simulated ? "is-simulated" : ""}`}
             aria-labelledby="source-change-title">
      <div className="source-change-header">
        <div>
          <span className="source-change-label">SIMULATED SOURCE CHANGE — OFFLINE DEMO ONLY</span>
          <h2 id="source-change-title">Source Change Recheck</h2>
          <p>This prepared sample scenario demonstrates why an earlier finding may need checking after a policy update. It is not a new live AI verification.</p>
        </div>
        {simulated && <span className="source-change-state">Simulation active</span>}
      </div>
      {!simulated ? (
        <>
          <div className="source-change-before">
            <div className="source-change-fact">
              <span>Original source cap</span>
              <strong>₹25,000</strong>
            </div>
            <div className="source-change-fact">
              <span>Previously detected finding</span>
              <strong className="verdict-contradicted">CONTRADICTED</strong>
            </div>
            <p>The original finding was based on the older source version, which capped reimbursement at ₹25,000.</p>
          </div>
          <button type="button" className="primary-button" onClick={onSimulate}>
            Simulate Policy Update
          </button>
        </>
      ) : (
        <>
          <div className="source-change-facts">
            <div className="source-change-fact">
              <span>Previous source cap</span>
              <strong>₹25,000</strong>
            </div>
            <div className="source-change-arrow" aria-hidden="true">→</div>
            <div className="source-change-fact updated">
              <span>Updated source cap</span>
              <strong>₹50,000</strong>
            </div>
            <div className="source-change-fact">
              <span>Previous verdict</span>
              <strong className="verdict-contradicted">CONTRADICTED</strong>
            </div>
            <div className="source-change-arrow" aria-hidden="true">→</div>
            <div className="source-change-fact updated">
              <span>Demonstration result after recheck</span>
              <strong className="verdict-supported">{currentVerification?.verdict || "Not available"}</strong>
            </div>
          </div>
          <blockquote className="source-change-quote">{UPDATED_REIMBURSEMENT_PASSAGE}</blockquote>
          <p className="source-change-explanation">The updated sample source now matches the document’s ₹50,000 claim. This prepared demonstration changes the sample result locally; it does not rerun verification.</p>
          <div className="source-change-comparison" aria-label="Before and after sample assessment">
            <div>
              <span>Before · trust score</span>
              <strong>{previousScore.trust_score}/100</strong>
              <small>{previousScore.finding_count} findings</small>
            </div>
            <span className="source-change-arrow" aria-hidden="true">→</span>
            <div>
              <span>After · trust score</span>
              <strong>{currentScore.trust_score}/100</strong>
              <small>{currentScore.finding_count} findings</small>
            </div>
          </div>
          <button type="button" className="secondary-button" onClick={onReset}>Reset Simulation</button>
        </>
      )}
    </section>
  );
}

function InputPanel({
  title,
  hint,
  value,
  onChange,
  onFileRead,
  onFileReadStart,
  isFileReadCurrent,
  onFileReadError,
  number,
}) {
  const fileReadId = useRef(0);
  return (
    <section className="input-panel">
      <div className="input-title">
        <span className="input-number">{number}</span>
        <div>
          <h2>{title}</h2>
          <p>{hint}</p>
        </div>
        <label className="upload-button">
          Upload .txt
          <input className="visually-hidden" type="file" accept=".txt,.md,text/plain"
                 aria-label={`Upload ${title} text file`}
                 onChange={(e) => {
                   const file = e.target.files[0];
                   if (file) {
                     const fileReadIdForRequest = ++fileReadId.current;
                     const inputRevision = onFileReadStart();
                     const isCurrent = () => fileReadIdForRequest === fileReadId.current
                       && isFileReadCurrent(inputRevision);
                     readTextFile(
                       file,
                       (text) => {
                         if (isCurrent()) onFileRead(text);
                       },
                       () => {
                         if (isCurrent()) onFileReadError();
                       },
                     );
                   }
                   e.target.value = "";
                 }} />
        </label>
      </div>
      <textarea aria-label={title} value={value} onChange={(e) => {
        fileReadId.current += 1;
        onChange(e.target.value);
      }}
                placeholder={hint} rows={9} />
      <span className="input-footnote">Plain text · Markdown · Up to the app’s text limit</span>
    </section>
  );
}

function Summary({ result, reviewedCount }) {
  const { score } = result;
  return (
    <section className={`summary status-${result.status}`} aria-label="Document assessment summary">
      <div className="summary-top">
        <div className="status-block">
          <span className={`status-dot status-${result.status}`} />
          <div>
            <span className="label">System status</span>
            <strong className={`status-text status-${result.status}`}>{result.status}</strong>
          </div>
        </div>
        <div className="summary-metric trust-metric">
          <span className="label">Trust score</span>
          <strong>{Math.round(score.trust_score)}<small> / 100</small></strong>
          <span className="metric-caption">Review score, not probability of truth</span>
        </div>
        <div className="summary-metric">
          <span className="label">Evidence coverage</span>
          <strong>{score.evidence_coverage}<small>%</small></strong>
          <span className="metric-caption">Claims with source passages retrieved</span>
        </div>
        <div className="summary-metric progress-metric">
          <span className="label">Review decisions</span>
          <strong>{reviewedCount}<small> / {score.finding_count}</small></strong>
          <span className="metric-caption">Confirmed or marked not an issue</span>
        </div>
      </div>
      <div className="summary-bottom">
        <span className="counts-label">Findings by consequence</span>
        <div className="counts" aria-label="Finding counts by consequence">
          {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((level) => (
            <span className="count-item" key={level}>
              <span className={`count-dot ${level}`} />
              {level.charAt(0) + level.slice(1).toLowerCase()}
              <strong>{score[`${level.toLowerCase()}_count`]}</strong>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function FindingQueueItem({ view, rank, decision, selected, onSelect }) {
  const { finding, affectedText } = view;
  return (
    <button type="button" className={`queue-item ${finding.consequence} ${selected ? "selected" : ""}`}
            aria-pressed={selected} onClick={onSelect}>
      <span className="queue-rank">{String(rank).padStart(2, "0")}</span>
      <span className="queue-content">
        <span className="queue-meta">
          <span className={`consequence-label ${finding.consequence}`}>{finding.consequence}</span>
          {finding.verdict && <span className="queue-verdict">{finding.verdict}</span>}
          {finding.risk_type && <span className="queue-type">{finding.risk_type.replaceAll("_", " ")}</span>}
        </span>
        <span className="queue-excerpt">{affectedText || "Finding text is unavailable."}</span>
        <span className="queue-foot">
          <span className="priority-badge">
            <span>Priority</span>
            <strong>{Math.round(finding.priority_score)}</strong>
          </span>
          {decision === "accepted" && <span className="decision-state">Confirmed — Open</span>}
          {decision === "dismissed" && <span className="decision-state">Not an issue</span>}
        </span>
      </span>
      <span className="queue-chevron" aria-hidden="true">›</span>
    </button>
  );
}

function EvidenceSection({ view }) {
  const { finding, claim, verification, evidenceChunks, evidenceQuote } = view;
  const verdict = finding.verdict || verification?.verdict;

  if (finding.risk_type === "SENSITIVE_DATA") {
    return (
      <section className="detail-section">
        <h3>Evidence and privacy</h3>
        <p className="body-copy">This is a sensitive-data finding, not a source-verification verdict. Only the masked value is shown.</p>
        {finding.matched_text && <blockquote className="masked-quote">{finding.matched_text}</blockquote>}
      </section>
    );
  }

  if (verdict === "CONTRADICTED") {
    return (
      <section className="detail-section">
        <h3>Document claim vs. source</h3>
        {claim?.claim_text && evidenceQuote ? (
          <div className="comparison">
            <div className="comparison-side document-side">
              <span className="label">AI-written document</span>
              <p>{claim.claim_text}</p>
            </div>
            <div className="comparison-side source-side">
              <span className="label">Source says</span>
              <p>“{evidenceQuote}”</p>
            </div>
          </div>
        ) : (
          <p className="fallback">A comparison cannot be shown because the document claim or quoted source passage is unavailable.</p>
        )}
        <EvidenceSources chunks={evidenceChunks} verification={verification} />
      </section>
    );
  }

  if (verdict === "UNSUPPORTED") {
    return (
      <section className="detail-section">
        <h3>Source evidence</h3>
        <p className="evidence-note">The supplied source does not substantiate this claim. That does not by itself mean the claim is false.</p>
        <EvidenceSources chunks={evidenceChunks} verification={verification} />
      </section>
    );
  }

  if (verdict === "UNCLEAR") {
    return (
      <section className="detail-section">
        <h3>Source evidence</h3>
        <p className="evidence-note">{verification?.explanation || "The system could not make a confident assessment from the available evidence."}</p>
        <EvidenceSources chunks={evidenceChunks} verification={verification} />
      </section>
    );
  }

  return (
    <section className="detail-section">
      <h3>{verdict === "SUPPORTED" ? "Supporting source evidence" : "Source evidence"}</h3>
      {evidenceQuote
        ? <blockquote className="source-quote">“{evidenceQuote}”</blockquote>
        : <p className="fallback">{verdict === "SUPPORTED"
          ? "No supporting quote was returned."
          : "No source passage is available for this finding."}</p>}
      <EvidenceSources chunks={evidenceChunks} verification={verification} />
    </section>
  );
}

function EvidenceSources({ chunks, verification }) {
  if (chunks.length > 0) {
    return (
      <ul className="source-list">
        {chunks.map((chunk) => (
          <li key={chunk.chunk_id}>
            <span>{chunk.source_id}</span>
            <span>{chunk.chunk_id}</span>
            {chunk.page != null && <span>Page {chunk.page}</span>}
          </li>
        ))}
      </ul>
    );
  }
  if (verification?.evidence_chunk_ids?.length) {
    return <p className="source-meta">Chunk {verification.evidence_chunk_ids.join(", ")}</p>;
  }
  return <p className="source-meta">No source or chunk reference was returned.</p>;
}

function FindingDetails({ view, rank, decision, onDecide }) {
  const { finding, claim, verification, affectedText, sentenceId } = view;
  const isDismissed = decision === "dismissed";
  const isSensitive = finding.risk_type === "SENSITIVE_DATA";
  const breakdown = priorityBreakdown(finding);
  const verdict = finding.verdict || verification?.verdict;
  const assessment = isSensitive ? "Sensitive data"
    : finding.risk_type === "RISKY_COMMITMENT" ? "Risky commitment"
      : verdict || "Not verified";

  return (
    <article className="detail-panel" aria-label="Selected finding details">
      <div className="detail-header">
        <div>
          <span className="eyebrow">{rank === 1 ? "Highest priority" : `Finding ${String(rank).padStart(2, "0")}`} · Priority {Math.round(finding.priority_score)}</span>
          <h2>{rank === 1 ? "Start your review here" : "Review this finding"}</h2>
        </div>
        {decision === "accepted" && <span className="review-chip confirmed">Confirmed — Open</span>}
        {isDismissed && <span className="review-chip dismissed">Not an issue</span>}
      </div>

      <section className="detail-section affected-section">
        <h3>Affected text</h3>
        <blockquote className="claim-quote">{affectedText || "The affected text is unavailable."}</blockquote>
        {claim?.claim_text && view.sentence && claim.claim_text !== view.sentence.text && (
          <p className="context-line"><span className="label">In sentence {sentenceId}</span>{view.sentence.text}</p>
        )}
        {finding.risk_type === "RISKY_COMMITMENT" && finding.matched_text && (
          <p className="risk-wording"><span className="label">Risky wording detected</span>{finding.matched_text}</p>
        )}
      </section>

      <section className="detail-section assessment-section">
        <h3>System assessment</h3>
        <div className="assessment-heading">
          <span className={`assessment-mark ${finding.consequence}`} />
          <strong>{assessment}</strong>
          {finding.risk_type === "RISKY_COMMITMENT" && verdict && (
            <span className="queue-verdict">{verdict}</span>
          )}
          <span className={`consequence-label ${finding.consequence}`}>{finding.consequence} consequence</span>
        </div>
        <p className="body-copy">{verification?.explanation || finding.reason || "No explanation was returned for this finding."}</p>
        {finding.reason && finding.reason !== verification?.explanation && (
          <p className="reason-copy">{finding.reason}</p>
        )}
      </section>

      <section className="detail-section ranking-section">
        <h3>Why this priority</h3>
        <p className="body-copy">The review queue ranks higher priority scores first. This score combines consequence, verdict, and any risk flag.</p>
        <div className="priority-breakdown">
          {breakdown.map((part) => (
            <span key={part.label}>{part.label}<strong>+{part.points}</strong></span>
          ))}
        </div>
        <p className="priority-total">Backend priority score <strong>{Math.round(finding.priority_score)} / 100</strong></p>
      </section>

      <EvidenceSection view={view} />

      <section className="recommended-callout" aria-label="Recommended next step">
        <span className="label">Recommended next step</span>
        <p>{finding.recommended_action || "Review the source and decide what should happen next."}</p>
      </section>

      <div className="review-actions" aria-label="Local reviewer actions">
        {isDismissed ? (
          <button type="button" className="secondary-button" onClick={() => onDecide(undefined)}>Restore to queue</button>
        ) : (
          <>
            <button type="button" className={`confirm-button ${decision === "accepted" ? "is-confirmed" : ""}`}
                    onClick={() => onDecide(decision === "accepted" ? undefined : "accepted")}>
              {decision === "accepted" ? "Undo confirmation" : "Confirm issue"}
            </button>
            <button type="button" className="secondary-button" onClick={() => onDecide("dismissed")}>Not an issue</button>
          </>
        )}
        <span className="action-disclaimer">Local review state only. This does not change the system assessment or edit the document.</span>
      </div>
    </article>
  );
}

function DocumentContext({ sentences, severity, selectedSentenceId, onPick, refs }) {
  const [expanded, setExpanded] = useState(false);
  const selected = sentences.find((sentence) => sentence.sentence_id === selectedSentenceId);
  const shown = expanded ? sentences : selected ? [selected] : [];

  return (
    <section className="document-context" aria-label="Document context">
      <div className="document-head">
        <div>
          <span className="eyebrow">Document context</span>
          <h3>AI-written document</h3>
        </div>
        <button type="button" className="text-button" aria-expanded={expanded}
                onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Show selected passage" : "Show full document"}
        </button>
      </div>
      <p className="document-note">Sensitive values are masked. Select a highlighted sentence to open its finding.</p>
      <div className={`doc ${expanded ? "doc-expanded" : ""}`}>
        {shown.length > 0 ? shown.map((sentence) => (
          <button key={sentence.sentence_id} type="button"
                  ref={(el) => (refs.current[sentence.sentence_id] = el)}
                  className={`sentence ${severity[sentence.sentence_id] ? `hl ${severity[sentence.sentence_id]}` : ""} ${
                    selectedSentenceId === sentence.sentence_id ? "picked" : ""}`}
                  onClick={() => onPick(sentence.sentence_id)}>
            <span className="sid">{sentence.sentence_id}</span>
            <span>{sentence.text}</span>
          </button>
        )) : (
          <p className="fallback">No matching sentence is available for this finding. You can still review its evidence and rationale above.</p>
        )}
      </div>
    </section>
  );
}

export default function App() {
  const [documentText, setDocumentText] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [resultMode, setResultMode] = useState(null);
  const [sampleKind, setSampleKind] = useState(null);
  const [sourceChangeSimulated, setSourceChangeSimulated] = useState(false);
  const [sampleNotice, setSampleNotice] = useState("");
  const [decisions, setDecisions] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const [showDismissed, setShowDismissed] = useState(false);
  const [showInputs, setShowInputs] = useState(true);
  const workspaceRef = useRef(null);
  const sentenceRefs = useRef({});
  const inputRevisionRef = useRef(0);

  const views = useMemo(() => (result ? buildFindingViews(result) : []), [result]);
  const { open, dismissed } = useMemo(() => splitByReview(views, decisions), [views, decisions]);
  const severity = useMemo(() => sentenceSeverity(open), [open]);
  const selected = views.find((view) => view.finding.finding_id === selectedId) || null;
  const reviewedCount = views.filter((view) => decisions[view.finding.finding_id]).length;
  const selectedRank = selected ? views.indexOf(selected) + 1 : 0;

  useEffect(() => {
    const el = selected?.sentenceId && sentenceRefs.current[selected.sentenceId];
    if (el?.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedId]);

  async function run() {
    const requestRevision = inputRevisionRef.current;
    setLoading(true);
    setError("");
    setSampleNotice("");
    setSampleKind(null);
    setSourceChangeSimulated(false);
    try {
      const data = await analyzeDocument(documentText, sourceText);
      if (requestRevision !== inputRevisionRef.current) {
        setResult(null);
        setResultMode(null);
        setDecisions({});
        setSelectedId(null);
        setSampleNotice("Inputs changed while analysis was running. Its report was discarded; analyze again.");
        return;
      }
      setResult(data);
      setResultMode("live");
      setDecisions({});
      setSelectedId(data.ranked_findings[0]?.finding_id || null);
      setShowDismissed(false);
      setShowInputs(false);
      requestAnimationFrame(() => workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      if (requestRevision !== inputRevisionRef.current) return;
      setResult(null);
      setDecisions({});
      setSelectedId(null);
      setResultMode(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function invalidateForInputChange() {
    inputRevisionRef.current += 1;
    const next = assessmentAfterInputChange(Boolean(result || resultMode || loading));
    setResult(next.result);
    setResultMode(next.resultMode);
    setSampleKind(null);
    setSourceChangeSimulated(false);
    setDecisions(next.decisions);
    setSelectedId(next.selectedId);
    setShowDismissed(false);
    setSampleNotice(next.notice);
    setError("");
    return inputRevisionRef.current;
  }

  function updateInput(setter, value) {
    invalidateForInputChange();
    setter(value);
  }

  function completeFileRead(setter, value) {
    inputRevisionRef.current += 1;
    setter(value);
  }

  function loadSample(preset, report, kind) {
    inputRevisionRef.current += 1;
    setDocumentText(preset.document);
    setSourceText(preset.source);
    setResult(report);
    setResultMode("sample");
    setSampleKind(kind);
    setSourceChangeSimulated(false);
    setSampleNotice("");
    setError("");
    setDecisions({});
    setSelectedId(report.ranked_findings[0]?.finding_id || null);
    setShowDismissed(false);
    setShowInputs(false);
    requestAnimationFrame(() => workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function simulatePolicyUpdate() {
    const demo = createSourceChangeDemo();
    setResult(demo.report);
    setSourceText(demo.sourceText);
    setDecisions({});
    setSelectedId(demo.report.ranked_findings[0]?.finding_id || null);
    setShowDismissed(false);
    setSourceChangeSimulated(true);
  }

  function resetPolicyUpdate() {
    const demo = resetSourceChangeDemo();
    setResult(demo.report);
    setSourceText(demo.sourceText);
    setDecisions({});
    setSelectedId(demo.report.ranked_findings[0]?.finding_id || null);
    setShowDismissed(false);
    setSourceChangeSimulated(false);
  }

  function decide(id, value) {
    if (!id) return;
    setDecisions((current) => {
      const next = { ...current };
      if (value) next[id] = value;
      else delete next[id];
      return next;
    });
  }

  function selectFinding(view) {
    setSelectedId(view.finding.finding_id);
    if (decisions[view.finding.finding_id] === "dismissed") setShowDismissed(true);
  }

  function pickSentence(sentenceId) {
    const first = open.find((view) => view.sentenceId === sentenceId);
    if (!first) return setSelectedId(null);
    setSelectedId(first.finding.finding_id);
    document.getElementById(`finding-${first.finding.finding_id}`)?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }

  const canRun = documentText.trim() && sourceText.trim() && !loading;

  return (
    <main className="app">
      <header className="app-header">
        <a className="brand" href="#" aria-label="AI Document Review home">
          <BrandMark />
          <span>AI Document Review</span>
        </a>
        <div className="header-caption">EVIDENCE REVIEW WORKSPACE</div>
      </header>

      <section className="intro">
        <span className="eyebrow">Evidence-led document review</span>
        <h1>See what your AI-written document gets right—and what needs a closer look.</h1>
        <p>Compare a document with its source material. Review important claims, the evidence behind them, and the issues that may need attention.</p>
      </section>

      {(!result || showInputs) && (
        <section className="input-workspace" aria-label="Documents to review">
          {result && (
            <div className="edit-heading">
              <div><h2>Update source documents</h2><p>Run a new analysis to replace the current assessment.</p></div>
              <button type="button" className="text-button" onClick={() => setShowInputs(false)}>Close</button>
            </div>
          )}
          <section className="sample-explorer" aria-labelledby="sample-explorer-title">
            <div className="section-intro">
              <span className="eyebrow">Start with an example</span>
              <h2 id="sample-explorer-title">Explore an offline sample</h2>
              <p>See how the review works without using the live AI service.</p>
            </div>
            <div className="sample-grid">
              <SampleCard
                tone="good"
                title="Explore a good document"
                description="See a document whose claims match the supplied policy evidence."
                detail="A sample report · No live analysis"
                onClick={() => loadSample(GOOD_PRESET, GOOD_SAMPLE_REPORT, "good")}
              />
              <SampleCard
                tone="risky"
                title="Explore a risky document"
                description="Preview conflicting claims, an unsupported statement, a risky promise, and masked sensitive data."
                detail="A sample report · No live analysis"
                onClick={() => loadSample(FLAWED_PRESET, FLAWED_SAMPLE_REPORT, "flawed")}
              />
            </div>
          </section>
          <div className="live-input-heading">
            <span className="eyebrow">Your documents</span>
            <h2>Or analyze your own documents</h2>
            <p>Your text is checked against the source material you provide.</p>
          </div>
          <div className="inputs">
            <InputPanel number="01" title="AI-written document" hint="Paste the document you want to review."
                        value={documentText} onChange={(value) => updateInput(setDocumentText, value)}
                        onFileRead={(value) => completeFileRead(setDocumentText, value)}
                        onFileReadStart={invalidateForInputChange}
                        isFileReadCurrent={(revision) => revision === inputRevisionRef.current}
                        onFileReadError={() => setError("The selected file could not be read. Choose a valid text file and try again.")} />
            <InputPanel number="02" title="Source material" hint="Paste the trusted material the document should be checked against."
                        value={sourceText} onChange={(value) => updateInput(setSourceText, value)}
                        onFileRead={(value) => completeFileRead(setSourceText, value)}
                        onFileReadStart={invalidateForInputChange}
                        isFileReadCurrent={(revision) => revision === inputRevisionRef.current}
                        onFileReadError={() => setError("The selected file could not be read. Choose a valid text file and try again.")} />
          </div>
          <div className="toolbar">
            <button className="primary-button" type="button" onClick={run} disabled={!canRun}>
              {loading ? <><span className="spinner" aria-hidden="true" /> Analyzing…</> : "Analyze document"}
            </button>
            <span className="live-analysis-note">Live analysis uses the AI service. It does not fall back to a sample report.</span>
            {loading && <span role="status" className="muted">Checking claims against the source. This can take a few seconds…</span>}
          </div>
        </section>
      )}

      {sampleNotice && <div className="sample-notice" role="status">{sampleNotice}</div>}

      {result && !showInputs && (
        <div className="edit-documents">
          <span>Assessment of the current document and source</span>
          <button type="button" className="text-button" onClick={() => setShowInputs(true)}>Edit documents</button>
        </div>
      )}

      {error && <div className="error" role="alert">{error}</div>}

      {result && (
        <section className="review-workspace" ref={workspaceRef} aria-label="Document review workspace">
          <div className={`result-mode ${resultMode === "sample" ? "sample" : "live"}`} role="status">
            {resultMode === "sample"
              ? "SAMPLE REPORT — NOT A LIVE ANALYSIS · Offline example"
              : "LIVE ANALYSIS · Result from the AI service"}
          </div>
          <Summary result={result} reviewedCount={reviewedCount} />
          {resultMode === "sample" && sampleKind === "flawed" && (
            <SourceChangeRecheck
              report={result}
              simulated={sourceChangeSimulated}
              onSimulate={simulatePolicyUpdate}
              onReset={resetPolicyUpdate}
            />
          )}
          <div className="workspace-heading">
            <div>
              <span className="eyebrow">Review workspace</span>
              <h2>Ranked findings</h2>
            </div>
            <span className="queue-count">{open.length} open · {dismissed.length} not an issue</span>
          </div>

          <div className="review-layout">
            <section className="queue-panel" aria-label="Ranked findings queue">
              <div className="queue-panel-head">
                <h3>Needs attention</h3>
                <span>{open.length}</span>
              </div>
              {open.length === 0 ? (
                <p className="empty-queue">No findings remain open. This does not change the system assessment above.</p>
              ) : (
                <div className="queue-list">
                  {open.map((view) => {
                    const rank = views.indexOf(view) + 1;
                    return (
                      <FindingQueueItem key={view.finding.finding_id} view={view} rank={rank}
                        decision={decisions[view.finding.finding_id]}
                        selected={selectedId === view.finding.finding_id}
                        onSelect={() => selectFinding(view)} />
                    );
                  })}
                </div>
              )}
              {dismissed.length > 0 && (
                <div className="dismissed-group">
                  <button type="button" className="dismissed-toggle" aria-expanded={showDismissed}
                          onClick={() => setShowDismissed((value) => !value)}>
                    <span>{showDismissed ? "−" : "+"}</span>
                    Not an issue <strong>{dismissed.length}</strong>
                  </button>
                  {showDismissed && (
                    <div className="queue-list dismissed-list">
                      {dismissed.map((view) => (
                        <FindingQueueItem key={view.finding.finding_id} view={view}
                          rank={views.indexOf(view) + 1} decision="dismissed"
                          selected={selectedId === view.finding.finding_id}
                          onSelect={() => selectFinding(view)} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>

            <div className="detail-column">
              {selected ? (
                <FindingDetails view={selected} rank={selectedRank}
                  decision={decisions[selected.finding.finding_id]}
                  onDecide={(value) => decide(selected.finding.finding_id, value)} />
              ) : (
                <section className="detail-panel no-selection">
                  <span className="eyebrow">Assessment complete</span>
                  <h2>No findings to review</h2>
                  <p className="body-copy">The system found no items requiring review under its configured policy. This is not a guarantee that every statement is true.</p>
                </section>
              )}
              <DocumentContext sentences={result.sentences} severity={severity}
                refs={sentenceRefs} selectedSentenceId={selected?.sentenceId}
                onPick={pickSentence} />
            </div>
          </div>
        </section>
      )}
      <footer className="footer">System assessments are evidence-based signals for human review, not a substitute for judgment.</footer>
    </main>
  );
}
