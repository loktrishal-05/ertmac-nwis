import { reasonInfo, reviewGate, reviewSegments } from './identifierReview.js'

// Presentational only: the raw transcript is displayed exactly and never edited here.
export function TranscriptReview({ result, acknowledged = [], confirmed = false, onAcknowledge, onConfirm }) {
  const flags = result?.identifier_review || []
  const identifiers = result?.technical_identifiers || []
  const gate = reviewGate({ result, acknowledged, confirmed })
  return <section className="transcript-review" aria-labelledby="transcript-review-title">
    <header>
      <h3 id="transcript-review-title">Review the voice transcript</h3>
      <p>Nothing has been corrected automatically. Fix any identifier in the question field below, then confirm each flag.</p>
    </header>
    <p className="raw-label">Raw transcript (exactly as recognised{result?.detected_language ? `, language: ${result.detected_language}` : ''})</p>
    <p className="raw-transcript" lang={result?.language?.effective || undefined} data-testid="raw-transcript">
      {reviewSegments(result?.text, flags).map((segment, index) => segment.flag === null
        ? <span key={index}>{segment.text}</span>
        // The flag number is CSS-generated so it is never selected, copied or read as part of the identifier.
        : <mark key={index} className="flagged-span" aria-describedby={`flag-${segment.flag}`} data-flag={segment.flag + 1}>{segment.text}</mark>)}
    </p>
    {!!identifiers.length && <div className="identifier-chips" aria-label="Recognised technical identifiers">
      <span className="raw-label">Recognised identifiers:</span>
      {identifiers.map((item, index) => <code key={index} className="chip">{item.text}</code>)}
    </div>}
    {flags.length ? <ol className="flag-list">{flags.map((flag, index) => <li key={index} id={`flag-${index}`} className={acknowledged.includes(index) ? 'is-checked' : ''}>
      <div className="flag-head"><span className="flag-number" aria-hidden="true">{index + 1}</span><code>{flag.text}</code></div>
      <ul className="flag-reasons">{(flag.reasons?.length ? flag.reasons : ['unknown']).map(reason => {
        const info = reasonInfo(reason)
        return <li key={reason}><strong>{info.label}.</strong> {info.help}</li>
      })}</ul>
      <label className="check"><input type="checkbox" checked={acknowledged.includes(index)} onChange={event => onAcknowledge?.(index, event.target.checked)} />
        I checked “{flag.text}” and corrected it in the question field if needed</label>
    </li>)}</ol> : <p className="muted">No identifier warnings were raised. Still read the transcript before submitting.</p>}
    <label className="check confirm"><input type="checkbox" checked={confirmed} onChange={event => onConfirm?.(event.target.checked)} />
      I reviewed the whole transcript and the question below is what I intend to ask</label>
    <p className={gate.ready ? 'gate ready' : 'gate'} role="status" aria-live="polite">
      {gate.ready ? 'Review complete. You can submit the question.' : `${gate.total - gate.pending.length} of ${gate.total} flags reviewed${confirmed ? '' : '; transcript confirmation pending'}.`}
    </p>
  </section>
}

// Submission form separated so the gate is enforced and testable in one place.
export function QueryForm({ query, onChange, onSubmit, gate, loading, label = 'Question', submitLabel = 'Submit query', reviewing = false }) {
  const blocked = !gate.ready
  return <form onSubmit={event => { event.preventDefault(); if (!blocked && query.trim() && !loading) onSubmit() }}>
    <label>{reviewing ? 'Question (correct the transcript here; the original above stays unchanged)' : label}
      <textarea value={query} onChange={event => onChange(event.target.value)} required maxLength={10000} rows={4}
        aria-describedby={blocked ? 'submit-gate' : undefined} /></label>
    {blocked && <p id="submit-gate" className="review-notice">Submission is locked until every flagged identifier is checked and the transcript is confirmed.</p>}
    <button type="submit" disabled={loading || !query.trim() || blocked} className="primary">{submitLabel}</button>
  </form>
}
