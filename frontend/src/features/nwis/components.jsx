import { useEffect, useId, useRef } from 'react'
import { Link } from 'react-router'
import { ErrorState, Icon, LoadingState } from '../../components/ui.jsx'
import { LOOKAHEAD_M, RADIUS_PRESETS_KM, SCORE_COMPONENTS, fmtAge, fmtKm, fmtM, fmtPct, fmtScore, hazardLabel, humanize, isSynthetic, num, riskLevel } from './nwisModel.js'
import { useNwis } from './NwisContext.jsx'

// Loading / unavailable / not-found for one NWIS endpoint. Never a fake zero.
export function NwisState({ request, what = 'this data', empty }) {
  if (request.loading) return <LoadingState label={`Loading ${what}…`} />
  if (request.error) {
    const { status, message } = request.error
    if (status === 404) return <div className="state state-empty"><strong>Not available</strong><p>{message}</p></div>
    if (status === 401 || status === 403) return <ErrorState title="Access restricted" message={message} />
    return <ErrorState title={`NWIS backend unavailable for ${what}`} onRetry={request.refresh}
      message={`${message} No values are shown until the NWIS API responds (integration dependency).`} />
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
export function EventDots({ counts = {} }) {
  const entries = Object.entries(counts)
  if (!entries.length) return <span className="muted small">None</span>
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
    <dt>{label}{weights?.[key] != null && <small> · w {weights[key]}</small>}</dt><dd><ScoreBar value={offset.components[key]} label={label} /></dd></div>)}
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

export function ContributionSplit({ historical, telemetry }) {
  if (historical == null && telemetry == null) return null
  const h = Math.round((historical ?? 0) * 100), t = Math.round((telemetry ?? 0) * 100)
  return <div className="nw-split"><span className="nw-split-bar" aria-hidden="true"><span style={{ width: `${h}%` }} /><span style={{ width: `${t}%` }} /></span>
    <span className="nw-split-legend"><span><i data-k="h" />Historical offsets {h}%</span><span><i data-k="t" />Live telemetry {t}%</span></span></div>
}

export function RiskCard({ hazard, lookahead, onWhy, compact = false }) {
  const level = riskLevel(hazard)
  const titleId = useId()
  return <article className="nw-risk" data-level={level} aria-labelledby={titleId}>
    <header><h3 id={titleId}>{hazardLabel(hazard.type)} risk</h3><TrendBadge trend={hazard.trend} /></header>
    <p className="nw-risk-main"><span className="nw-prob">{fmtPct(hazard.probability)}</span><span className="muted">probability · next {lookahead} m<br /><span className="nw-level">{humanize(level)}</span></span></p>
    <div className="nw-meter"><span>Confidence</span><ScoreBar value={hazard.confidence} label="Confidence" /></div>
    {!compact && hazard.series.length > 1 && <Sparkline values={hazard.series.map(p => p.probability)} label={`${hazardLabel(hazard.type)} probability trend: ${hazard.series.map(p => fmtPct(p.probability)).join(', ')}`} />}
    <dl className="nw-risk-facts">
      <div><dt>Supporting wells</dt><dd>{hazard.wells.length ? hazard.wells.join(', ') : 'None'}</dd></div>
      <div><dt>Evidence</dt><dd>{hazard.evidenceCount} record{hazard.evidenceCount === 1 ? '' : 's'}</dd></div>
      {!compact && <div><dt>Top factors</dt><dd>{hazard.factors.length ? hazard.factors.map(humanize).join(' · ') : '—'}</dd></div>}
      <div><dt>Telemetry freshness</dt><dd>{hazard.freshnessS == null ? 'Historical only' : fmtAge(hazard.freshnessS)}</dd></div>
    </dl>
    {!compact && <ContributionSplit historical={hazard.historical} telemetry={hazard.telemetry} />}
    <footer>{onWhy && <button type="button" onClick={() => onWhy(hazard)}><Icon name="search" size={16} />Why this alert?</button>}
      {hazard.advisoryId && <Link className="button ghost" to={`/app/advisories?id=${encodeURIComponent(hazard.advisoryId)}`}>Advisory {hazard.advisoryId}</Link>}</footer>
  </article>
}

// "Why this alert?": engineering evidence only — offsets, event depths, citations, telemetry features, gaps.
export function EvidenceDrawer({ hazard, risk, offsets = [], onClose }) {
  const dialog = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const element = dialog.current
    if (hazard && element && !element.open) element.showModal?.()
    if (!hazard && element?.open) element.close()
  }, [hazard])
  const evidence = (risk?.evidence || []).filter(e => hazard?.evidenceIds.includes(e.id))
  const byId = new Map(offsets.map(o => [o.id, o]))
  return <dialog ref={dialog} className="nw-drawer" aria-labelledby={titleId} onClose={onClose}>
    {hazard && <>
      <header className="nw-drawer-head">
        <div><p className="nw-eyebrow">Why this alert?</p><h2 id={titleId}>{hazardLabel(hazard.type)} · {fmtPct(hazard.probability)} over the next {risk?.lookahead_m} m</h2>
          <p className="muted small">Confidence {fmtPct(hazard.confidence)} · {risk?.model_version || 'model version not reported'} · as of {risk?.as_of ? new Date(risk.as_of).toLocaleString() : '—'}</p></div>
        <button type="button" className="icon-button" onClick={() => dialog.current?.close()} aria-label="Close evidence"><Icon name="close" /></button>
      </header>
      <section><h3>Supporting offset wells</h3>
        {hazard.wells.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Supporting offset wells"><table><thead><tr><th>Well</th><th>Rank</th><th>Total</th><th>Formation</th><th>Depth</th><th>Distance</th></tr></thead>
          <tbody>{hazard.wells.map(id => { const o = byId.get(id); return <tr key={id}><td><Link to={`/app/wells/${encodeURIComponent(id)}`}>{id}</Link></td>
            <td className="num">{o?.rank ?? '—'}</td><td className="num">{fmtScore(o?.total)}</td><td className="num">{fmtScore(o?.components.formation)}</td><td className="num">{fmtScore(o?.components.depth)}</td><td className="num">{fmtKm(o?.distanceKm)}</td></tr> })}</tbody></table></div>
          : <p className="muted">No supporting offsets.</p>}
        {hazard.wells.some(id => !byId.has(id)) && <p className="muted small">Some wells are outside the current radius; widen it to see their component scores.</p>}
      </section>
      <section><h3>Historical events and citations</h3>
        {evidence.length ? <ol className="nw-evidence-list">{evidence.map(e => <li key={e.id}>
          <div className="nw-evidence-top"><DrillingEventChip type={e.type} severity={e.severity} /><strong>{e.well_id}</strong><span>{fmtM(e.depth_tvd_m)} TVD · {fmtM(e.depth_md_m)} MD</span><span>{e.formation || 'Formation unknown'}</span><VerificationBadge state={e.verification} /></div>
          <blockquote>“{e.raw_observation}”</blockquote>
          <p className="nw-cite"><Icon name="book" size={14} />{e.source?.report_id} · page {e.source?.page ?? '—'} · extraction confidence {fmtPct(e.confidence)}</p></li>)}</ol>
          : <p className="muted">{hazard.evidenceCount ? `${hazard.evidenceCount} evidence IDs returned without detail: ${hazard.evidenceIds.join(', ')}` : 'No evidence records returned.'}</p>}
      </section>
      <section><h3>Live telemetry features</h3>
        {hazard.telemetryFeatures.length ? <ul>{hazard.telemetryFeatures.map(f => <li key={f}>{f}</li>)}</ul> : <p className="muted">No telemetry contribution to this assessment.</p>}
        <ContributionSplit historical={hazard.historical} telemetry={hazard.telemetry} /></section>
      <section><h3>Missing evidence</h3>{hazard.missing.length ? <ul className="nw-missing">{hazard.missing.map(m => <li key={m}>{m}</li>)}</ul> : <p className="muted">None reported.</p>}</section>
      <section><h3>Confidence explanation</h3><p>{hazard.confidenceNote || 'Not reported by the risk engine.'}</p></section>
      <p className="nw-advisory-note"><Icon name="shield" size={16} />Advisory only. This is the engineering evidence behind the score, not a control instruction; the drilling engineer decides.</p>
    </>}
  </dialog>
}
