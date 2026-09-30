import { useEffect, useId, useRef } from 'react'
import { Link } from 'react-router'
import { ErrorState, Icon, LoadingState } from '../../components/ui.jsx'
import { LOOKAHEAD_M, RADIUS_PRESETS_KM, SCORE_COMPONENTS, fmtKm, fmtM, fmtPct, fmtScore, hazardLabel, humanize, isSynthetic, num, paths, riskLevel } from './nwisModel.js'
import { adaptAssessment } from './adapters.js'
import { useRequest, useResource } from '../../hooks/useApi.js'
import { useNwis } from './NwisContext.jsx'

// B2 refuses every NWIS read (403) until the user accepts the advisory terms. The text comes from the backend.
// If the terms endpoint itself fails, the pages render and show their own backend errors.
export function TermsGate({ children }) {
  const terms = useResource(paths.terms)
  const accept = useRequest()
  if (terms.error) return children
  if (!terms.data) return <LoadingState label="Checking NWIS advisory terms…" />
  if (terms.data.accepted) return children
  async function agree() {
    if (await accept.run(paths.termsAccept, { method: 'POST', body: { version: terms.data.version, accepted: true } })) terms.refresh()
  }
  return <section className="panel nw-panel nw-terms" aria-labelledby="terms-h">
    <h2 id="terms-h">NWIS advisory terms</h2>
    <p>{terms.data.text}</p>
    <p className="muted small">Version {terms.data.version}. Your acceptance is recorded on the audit log.</p>
    <button type="button" className="primary" disabled={accept.loading} onClick={agree}>{accept.loading ? 'Recording…' : 'Accept and continue'}</button>
    {accept.error && <p className="api-error" role="alert">{accept.error.message}</p>}
  </section>
}

// Loading / unavailable / not-found for one NWIS endpoint. Never a fake zero.
export function NwisState({ request, what = 'this data', empty }) {
  if (request.loading) return <LoadingState label={`Loading ${what}…`} />
  if (request.error) {
    const { status, message } = request.error
    if (status === 404) return <div className="state state-empty"><strong>Not available</strong><p>{message}</p></div>
    if (status === 409) return <ErrorState title="The record changed" message={`${message} Refresh to see the current state before acting again.`} onRetry={request.refresh} />
    if (status === 401 || status === 403) return <ErrorState title="Access restricted" message={message} />
    return <ErrorState title={`NWIS backend unavailable for ${what}`} onRetry={request.refresh}
      message={`${message} No values are shown until the NWIS API responds.`} />
  }
  if (empty) return <div className="state state-empty"><strong>{empty}</strong></div>
  return null
}

export function SyntheticDataBadge({ data, force = false }) {
  if (!force && !isSynthetic(data)) return null
  return <span className="nw-badge nw-synthetic" title="Every record here carries dataset_origin = synthetic_demo. Not Oil India data.">
    <Icon name="alert" size={13} />Synthetic demo dataset</span>
}

export function DataQualityBadge({ value, label = 'DQ' }) {
  if (num(value) == null) return <span className="nw-badge" data-quality="unknown">{label} unknown</span>
  const q = value >= 0.75 ? 'good' : value >= 0.5 ? 'fair' : 'poor'
  return <span className="nw-badge" data-quality={q} title={`Data quality score ${fmtScore(value)} (${q})`}>{label} {fmtScore(value)}</span>
}

export function DrillingEventChip({ type, severity, children }) {
  return <span className="nw-event-chip" data-type={type} data-severity={severity || undefined}><i aria-hidden="true" />{hazardLabel(type)}{children}</span>
}

// Compact per-type event counts for dense tables; the full list is the accessible label.
export function EventDots({ counts }) {
  const entries = Object.entries(counts ?? {})
  if (!entries.length) return <span className="muted small" title="Not reported in this response">—</span>
  const label = entries.map(([type, n]) => `${hazardLabel(type)} ×${n}`).join(', ')
  return <span className="nw-dots" role="img" aria-label={label} title={label}>{entries.map(([type, n]) => <span key={type} data-type={type}><i aria-hidden="true" />{n}</span>)}</span>
}

export function VerificationBadge({ state }) {
  if (!state) return null
  return <span className="nw-badge" data-verification={state}>{humanize(state)}</span>
}

// Segmented preset control (aria-pressed buttons).
function Segmented({ label, values, value, onChange, format }) {
  return <div className="nw-segmented" role="group" aria-label={label}><span className="nw-seg-label" aria-hidden="true">{label}</span>
    {values.map(v => <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{format(v)}</button>)}</div>
}
export function RadiusControl() {
  const { radiusKm, set } = useNwis()
  return <Segmented label="Radius" values={RADIUS_PRESETS_KM} value={radiusKm} onChange={v => set({ radiusKm: v })} format={v => `${v} km`} />
}
export function LookaheadControl() {
  const { lookahead, set } = useNwis()
  return <Segmented label="Look-ahead" values={LOOKAHEAD_M} value={lookahead} onChange={v => set({ lookahead: v })} format={v => `${v} m`} />
}

export function WellSelector() {
  const { wellId, wellList, set, wells } = useNwis()
  const id = useId()
  if (!wellList.length) return <span className="nw-badge">{wells.loading ? 'Loading wells…' : wellId || 'No well catalogue'}</span>
  const active = wellList.filter(w => w.role === 'active' || w.status === 'drilling')
  const rest = wellList.filter(w => !active.includes(w))
  return <label className="nw-well-select" htmlFor={id}><span>Active well</span>
    <select id={id} value={wellId || ''} onChange={event => set({ wellId: event.target.value })}>
      {active.length > 0 && <optgroup label="Drilling">{active.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</optgroup>}
      <optgroup label="Catalogue">{rest.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</optgroup>
    </select></label>
}

// The analyst context strip shown on every well-scoped page.
export function WellContextBar({ radius = false, lookahead = false }) {
  const { well } = useNwis()
  return <section className="nw-context" aria-label="Active well context">
    <WellSelector />
    <dl className="nw-context-facts">
      <div><dt>MD</dt><dd>{fmtM(well?.current_md_m)}</dd></div>
      <div><dt>TVD</dt><dd>{fmtM(well?.current_tvd_m)}</dd></div>
      <div><dt>Formation</dt><dd>{well?.current_formation || '—'}</dd></div>
      <div><dt>Section</dt><dd>{well?.hole_section || '—'}</dd></div>
    </dl>
    <div className="nw-context-controls">{radius && <RadiusControl />}{lookahead && <LookaheadControl />}</div>
    <SyntheticDataBadge data={well} />
  </section>
}

export function ScoreBar({ value, label }) {
  const v = num(value)
  return <span className="nw-score" title={label ? `${label}: ${fmtScore(v)}` : undefined}>
    <span className="nw-score-track" aria-hidden="true"><span style={{ width: `${Math.round((v ?? 0) * 100)}%` }} data-missing={v == null || undefined} /></span>
    <span className="nw-score-num">{fmtScore(v)}</span></span>
}

export function OffsetScoreBreakdown({ offset, weights }) {
  return <dl className="nw-breakdown">{SCORE_COMPONENTS.map(([key, label]) => <div key={key}>
    <dt>{label}{weights?.[key] != null && <small> · w {fmtScore(weights[key])}</small>}</dt><dd><ScoreBar value={offset.components[key]} label={label} /></dd></div>)}
  </dl>
}

export function Sparkline({ values, label, width = 120, height = 32 }) {
  const clean = values.filter(v => num(v) != null)
  if (clean.length < 2) return null
  const min = Math.min(...clean), max = Math.max(...clean), span = max - min || 1
  const pts = clean.map((v, i) => [(i / (clean.length - 1)) * (width - 4) + 2, height - 3 - ((v - min) / span) * (height - 6)])
  return <svg className="nw-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
    <polyline points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} /><circle cx={pts.at(-1)[0]} cy={pts.at(-1)[1]} r="2.5" /></svg>
}

const TREND = { rising: ['↑', 'Rising'], falling: ['↓', 'Falling'], steady: ['→', 'Steady'] }
export function TrendBadge({ trend }) {
  const [arrow, text] = TREND[trend] || ['·', 'No trend']
  return <span className="nw-trend" data-trend={trend || 'none'}><span aria-hidden="true">{arrow}</span> {text}</span>
}

// B2: historical exposure is a relevance-weighted share of analogs with the hazard; the live anomaly is a bounded
// additive modifier. They are shown as values, not as shares of 100%.
export function ContributionSplit({ historical, telemetry }) {
  if (historical == null && telemetry == null) return null
  return <dl className="nw-contrib">
    <div><dt>Historical exposure</dt><dd><ScoreBar value={historical} label="Historical exposure" /></dd></div>
    <div><dt>Live anomaly contribution</dt><dd>{telemetry == null ? 'Unavailable' : telemetry === 0 ? 'None detected' : `+${fmtScore(telemetry)}`}</dd></div>
  </dl>
}

const TELEMETRY_STATE = { fresh: 'Fresh', stale: 'Stale — not used', unavailable: 'Unavailable' }

export function RiskCard({ hazard, lookahead, onWhy, compact = false }) {
  const level = riskLevel(hazard)
  const titleId = useId()
  const noProbability = hazard.probability == null
  return <article className="nw-risk" data-level={level} aria-labelledby={titleId}>
    <header><h3 id={titleId}>{hazardLabel(hazard.type)} risk</h3><TrendBadge trend={hazard.trend} /></header>
    <p className="nw-risk-main"><span className="nw-prob">{noProbability ? '—' : fmtPct(hazard.probability)}</span><span className="muted">{noProbability ? 'Insufficient evidence' : 'uncalibrated estimate'} · next {lookahead} m<br /><span className="nw-level">{noProbability ? 'No usable analogs' : humanize(level)}</span></span></p>
    <div className="nw-meter"><span>Confidence</span><ScoreBar value={hazard.confidence} label="Confidence" /></div>
    <dl className="nw-risk-facts">
      <div><dt>Supporting wells</dt><dd>{hazard.wells.length ? hazard.wells.join(', ') : 'None'}</dd></div>
      <div><dt>Evidence</dt><dd>{hazard.evidenceCount ? `${hazard.evidenceCount} cited event${hazard.evidenceCount === 1 ? '' : 's'}` : 'No cited events'}</dd></div>
      {!compact && <div><dt>Top factors</dt><dd>{hazard.factors.length ? hazard.factors.map(humanize).join(' · ') : '—'}</dd></div>}
      <div><dt>Telemetry</dt><dd>{TELEMETRY_STATE[hazard.telemetryState] ?? 'Not reported'}{hazard.telemetryMode === 'replay' && hazard.telemetryState !== 'unavailable' ? ' (replay)' : ''}</dd></div>
    </dl>
    {!compact && <ContributionSplit historical={hazard.historical} telemetry={hazard.telemetry} />}
    <footer>{onWhy && <button type="button" onClick={() => onWhy(hazard)}><Icon name="search" size={16} />Why this alert?</button>}</footer>
  </article>
}

// "Why this alert?": the persisted assessment → risk evidence → drilling event → report → page chain (GET /api/assessments/{id}).
// Engineering evidence only; no model reasoning. If the assessment has not been recorded yet, the engineer can record it.
export function EvidenceDrawer({ hazard, risk, offsets = [], onClose, wellId, onRecorded }) {
  const dialog = useRef(null)
  const titleId = useId()
  const detail = useRequest()
  const record = useRequest()
  const { run } = detail
  useEffect(() => {
    const element = dialog.current
    if (hazard && element && !element.open) element.showModal?.()
    if (!hazard && element?.open) element.close()
    if (hazard?.assessmentId) run(paths.assessment(hazard.assessmentId))
  }, [hazard, run])
  const data = detail.data ? adaptAssessment(detail.data) : null
  const byId = new Map(offsets.map(o => [o.id, o]))
  async function recordAssessment() {
    const result = await record.run(paths.assess(wellId, risk?.lookahead_m), { method: 'POST', timeout: 60000 })
    if (result) { onRecorded?.(); run(paths.assessment(hazard.assessmentId)) }
  }
  return <dialog ref={dialog} className="nw-drawer" aria-labelledby={titleId} onClose={onClose}>
    {hazard && <>
      <header className="nw-drawer-head">
        <div><p className="nw-eyebrow">Why this alert?</p><h2 id={titleId}>{hazardLabel(hazard.type)} · {hazard.probability == null ? 'insufficient evidence' : `${fmtPct(hazard.probability)} (uncalibrated)`} over the next {risk?.lookahead_m} m</h2>
          <p className="muted small">Confidence {fmtPct(hazard.confidence)} · {risk?.model_version || 'model version not reported'} · as of {risk?.as_of ? new Date(risk.as_of).toLocaleString() : '—'} · assessment <code>{hazard.assessmentId?.slice(0, 12) ?? '—'}</code></p></div>
        <button type="button" className="icon-button" onClick={() => dialog.current?.close()} aria-label="Close evidence"><Icon name="close" /></button>
      </header>
      <section><h3>Supporting offset wells</h3>
        {hazard.wells.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Supporting offset wells"><table><thead><tr><th>Well</th><th>Rank</th><th>Total</th><th>Formation</th><th>Depth</th><th>Distance</th></tr></thead>
          <tbody>{hazard.wells.map(id => { const o = byId.get(id); return <tr key={id}><td><Link to={`/app/wells/${encodeURIComponent(id)}`}>{id}</Link></td>
            <td className="num">{o?.rank ?? '—'}</td><td className="num">{fmtScore(o?.total)}</td><td className="num">{fmtScore(o?.components.formation)}</td><td className="num">{fmtScore(o?.components.depth)}</td><td className="num">{fmtKm(o?.distanceKm)}</td></tr> })}</tbody></table></div>
          : <p className="muted">No supporting offsets.</p>}
      </section>
      <section><h3>Evidence chain: event → report → page</h3>
        {detail.loading && <p role="status">Loading the recorded assessment…</p>}
        {detail.error?.status === 404 && <div className="state state-empty"><strong>This assessment has not been recorded yet.</strong>
          <p>Risk shown on screen is computed read-only. Recording it persists the assessment, links each cited event and its source report hash, and evaluates the alert policy.</p>
          {wellId && <button type="button" className="primary" disabled={record.loading} onClick={recordAssessment}>{record.loading ? 'Recording…' : 'Record assessment'}</button>}
          {record.error && <p className="api-error" role="alert">{record.error.status === 403 ? 'Your role cannot record assessments. ' : ''}{record.error.message}</p>}</div>}
        {detail.error && detail.error.status !== 404 && <p className="api-error" role="alert">{detail.error.message}</p>}
        {data && (data.evidence.length ? <ol className="nw-evidence-list">{data.evidence.map(link => { const e = link.event
          return <li key={e.id}>
            <div className="nw-evidence-top"><DrillingEventChip type={e.type} severity={e.severity} /><strong>{e.well_id}</strong><span>{fmtM(e.depth_md_m)} MD · {fmtM(e.depth_tvd_m)} TVD</span><span>{e.formation || 'Formation not recorded'}</span><VerificationBadge state={e.verification} /></div>
            <blockquote>“{e.raw_observation || e.observation || 'No source wording recorded.'}”</blockquote>
            <p className="nw-cite"><Icon name="book" size={14} />{link.sourceUrl ? <a href={link.sourceUrl} target="_blank" rel="noreferrer">{e.source?.report_id} · page {e.source?.page ?? '—'}</a> : `${e.source?.report_id ?? 'report not linked'} · page ${e.source?.page ?? '—'}`}
              {' · '}event <code>{e.id}</code>{link.contribution != null ? ` · contribution ${fmtScore(link.contribution)}` : ''}</p>
            <p className="muted small">{link.reason ? `${link.reason} · ` : ''}{link.sourceHashMatches === false ? 'Source file changed since the assessment' : link.sourceHashMatches ? 'Source hash matches the assessment snapshot' : 'Source hash not recorded'}{link.changedSinceAssessment ? ' · event record changed since the assessment (snapshot preserved)' : ''}</p>
          </li> })}</ol> : <p className="muted">The recorded assessment cites no events.</p>)}
        {!hazard.assessmentId && <p className="muted">Evidence IDs: {hazard.evidenceIds.join(', ') || 'none'}</p>}
      </section>
      <section><h3>Live telemetry</h3>
        {hazard.telemetryFeatures.length ? <ul>{hazard.telemetryFeatures.map(f => <li key={f}>{f}</li>)}</ul> : <p className="muted">No telemetry anomaly contributed ({TELEMETRY_STATE[hazard.telemetryState] ?? 'not reported'}).</p>}
        <ContributionSplit historical={hazard.historical} telemetry={hazard.telemetry} /></section>
      <section><h3>Missing evidence</h3>{hazard.missing.length ? <ul className="nw-missing">{hazard.missing.map(m => <li key={m}>{humanize(m)}</li>)}</ul> : <p className="muted">None reported.</p>}</section>
      <section><h3>Confidence basis</h3><p>{hazard.confidenceNote || 'Not reported by the risk engine.'}</p>
        <p className="muted small">The probability is a heuristic exposure score (calibrated = false), not a validated field-event probability.</p></section>
      <p className="nw-advisory-note"><Icon name="shield" size={16} />Advisory only. This is the engineering evidence behind the score, not a control instruction; the drilling engineer decides.</p>
    </>}
  </dialog>
}
