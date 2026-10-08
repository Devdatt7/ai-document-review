import { useEffect, useMemo, useRef, useState } from "react";
import { analyzeDocument } from "./api.js";
import { DEMO_DOCUMENT, DEMO_SOURCE } from "./demo.js";
import { buildFindingViews, sentenceSeverity, splitByReview } from "./lib.js";
import "./styles.css";

function readTextFile(file, setter) {
  const reader = new FileReader();
  reader.onload = () => setter(String(reader.result || ""));
  reader.readAsText(file);
}

function InputPanel({ title, hint, value, onChange }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        <label className="link-button">
          Upload .txt
          <input type="file" accept=".txt,.md,text/plain" hidden
                 onChange={(e) => e.target.files[0] && readTextFile(e.target.files[0], onChange)} />
        </label>
      </div>
      <textarea aria-label={title} value={value} onChange={(e) => onChange(e.target.value)}
                placeholder={hint} rows={10} />
    </section>
  );
}

function Summary({ result, openCount }) {
  const s = result.score;
  return (
    <section className={`summary status-${result.status}`}>
      <div className="summary-main">
        <div className="metric"><span className="label">Trust Score</span>
          <span className="big">{Math.round(s.trust_score)}<small> / 100</small></span></div>
        <div className="metric"><span className="label">Evidence Coverage</span>
          <span className="big">{s.evidence_coverage}<small>%</small></span></div>
        <div className="metric"><span className="label">Status</span>
          <span className={`status-pill status-${result.status}`}>{result.status}</span></div>
        <div className="metric"><span className="label">Open findings</span>
          <span className="big">{openCount}</span></div>
      </div>
      <div className="counts">
        <span className="badge CRITICAL">Critical {s.critical_count}</span>
        <span className="badge HIGH">High {s.high_count}</span>
        <span className="badge MEDIUM">Medium {s.medium_count}</span>
        <span className="badge LOW">Low {s.low_count}</span>
      </div>
      <p className="note">
        Trust score is a review score under the configured policy, not a probability that the document is
        true. Status and score come from the backend; accept/dismiss below only change your review queue.
      </p>
    </section>
  );
}

function FindingCard({ view, decision, selected, onSelect, onDecide }) {
  const { finding, affectedText, evidenceQuote, evidenceChunks, verification } = view;
  const dismissed = decision === "dismissed";
  return (
    <article id={`finding-${finding.finding_id}`}
             className={`finding ${finding.consequence} ${selected ? "selected" : ""} ${dismissed ? "dismissed" : ""}`}
             onClick={onSelect}>
      <header>
        <span className={`badge ${finding.consequence}`}>{finding.consequence}</span>
        <span className="priority">Priority {Math.round(finding.priority_score)}</span>
        {finding.verdict && <span className="tag">{finding.verdict}</span>}
        {finding.risk_type && <span className="tag risk">{finding.risk_type.replace("_", " ")}</span>}
        {decision === "accepted" && <span className="tag accepted">Accepted / Open</span>}
        {dismissed && <span className="tag">Dismissed</span>}
      </header>

      {affectedText && <p className="affected">“{affectedText}”</p>}
      <p>{finding.reason}</p>
      {verification?.explanation && <p className="muted">{verification.explanation}</p>}

      {evidenceQuote ? (
        <blockquote className="evidence">
          <span className="label">Source evidence</span>
          “{evidenceQuote}”
          {evidenceChunks.length > 0 ? (
            <small>{evidenceChunks.map((c) =>
              `Source ${c.source_id} · Chunk ${c.chunk_id}${c.page ? ` · Page ${c.page}` : ""}`).join("  |  ")}</small>
          ) : verification?.evidence_chunk_ids?.length > 0 && (
            <small>Chunk {verification.evidence_chunk_ids.join(", ")}</small>
          )}
        </blockquote>
      ) : view.claim && (
        <p className="muted">No supporting source evidence was found for this claim.</p>
      )}

      <p className="action"><strong>Recommended action:</strong> {finding.recommended_action}</p>

      <div className="buttons" onClick={(e) => e.stopPropagation()}>
        {dismissed ? (
          <button onClick={() => onDecide(undefined)}>Restore</button>
        ) : (
          <>
            <button className={decision === "accepted" ? "active" : ""} onClick={() => onDecide("accepted")}>Accept</button>
            <button onClick={() => onDecide("dismissed")}>Dismiss</button>
          </>
        )}
      </div>
    </article>
  );
}

function DocumentView({ sentences, severity, selectedSentenceId, onPick, refs }) {
  return (
    <section className="panel">
      <h2>Analyzed document</h2>
      <p className="muted">Sensitive values are shown masked, exactly as returned by the backend.</p>
      <div className="doc">
        {sentences.map((s) => (
          <p key={s.sentence_id} ref={(el) => (refs.current[s.sentence_id] = el)}
             className={`sentence ${severity[s.sentence_id] ? `hl ${severity[s.sentence_id]}` : ""} ${
               selectedSentenceId === s.sentence_id ? "picked" : ""}`}
             onClick={() => onPick(s.sentence_id)}>
            <span className="sid">{s.sentence_id}</span> {s.text}
          </p>
        ))}
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
  const [decisions, setDecisions] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const [showDismissed, setShowDismissed] = useState(false);
  const sentenceRefs = useRef({});

  const views = useMemo(() => (result ? buildFindingViews(result) : []), [result]);
  const { open, dismissed } = useMemo(() => splitByReview(views, decisions), [views, decisions]);
  const severity = useMemo(() => sentenceSeverity(open), [open]);
  const selected = views.find((v) => v.finding.finding_id === selectedId);

  useEffect(() => {
    const el = selected?.sentenceId && sentenceRefs.current[selected.sentenceId];
    if (el?.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedId]);

  async function run() {
    setLoading(true);
    setError("");
    try {
      const data = await analyzeDocument(documentText, sourceText);
      setResult(data);
      setDecisions({});
      setSelectedId(null);
      setShowDismissed(false);
    } catch (e) {
      setResult(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function decide(id, value) {
    setDecisions((d) => {
      const next = { ...d };
      if (value) next[id] = value;
      else delete next[id];
      return next;
    });
  }

  function pickSentence(sentenceId) {
    const first = open.find((v) => v.sentenceId === sentenceId);
    if (!first) return setSelectedId(null);
    setSelectedId(first.finding.finding_id);
    document.getElementById(`finding-${first.finding.finding_id}`)?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }

  const canRun = documentText.trim() && sourceText.trim() && !loading;

  return (
    <main className="app">
      <header className="top">
        <h1>AI Document Review</h1>
        <p>Find what needs human attention before an AI-written document is trusted.</p>
      </header>

      <div className="inputs">
        <InputPanel title="AI-written document" hint="Paste the AI-written document here…"
                    value={documentText} onChange={setDocumentText} />
        <InputPanel title="Source material" hint="Paste the source the document should be checked against…"
                    value={sourceText} onChange={setSourceText} />
      </div>
      <div className="toolbar">
        <button className="primary" onClick={run} disabled={!canRun}>
          {loading ? "Analyzing…" : "Analyze Document"}
        </button>
        <button onClick={() => { setDocumentText(DEMO_DOCUMENT); setSourceText(DEMO_SOURCE); }} disabled={loading}>
          Load Demo
        </button>
        {loading && <span role="status" className="muted">Checking claims against the source. This can take a few seconds…</span>}
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      {result && (
        <>
          <Summary result={result} openCount={open.length} />
          <div className="results">
            <section>
              <h2>Findings queue ({open.length})</h2>
              {open.length === 0 && (
                <p className="muted">No open findings. This only means nothing currently detected needs review under the configured policy.</p>
              )}
              {open.map((v) => (
                <FindingCard key={v.finding.finding_id} view={v}
                             decision={decisions[v.finding.finding_id]}
                             selected={selectedId === v.finding.finding_id}
                             onSelect={() => setSelectedId(v.finding.finding_id)}
                             onDecide={(val) => decide(v.finding.finding_id, val)} />
              ))}

              <button className="link-button wide" onClick={() => setShowDismissed(!showDismissed)}>
                {showDismissed ? "▼" : "▶"} Dismissed Findings ({dismissed.length})
              </button>
              {showDismissed && dismissed.map((v) => (
                <FindingCard key={v.finding.finding_id} view={v} decision="dismissed"
                             selected={selectedId === v.finding.finding_id}
                             onSelect={() => setSelectedId(v.finding.finding_id)}
                             onDecide={(val) => decide(v.finding.finding_id, val)} />
              ))}
            </section>
            <DocumentView sentences={result.sentences} severity={severity} refs={sentenceRefs}
                          selectedSentenceId={selected?.sentenceId} onPick={pickSentence} />
          </div>
        </>
      )}
    </main>
  );
}
