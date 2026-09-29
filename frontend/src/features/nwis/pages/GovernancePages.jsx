import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Icon, PageHeader } from '../../../components/ui.jsx'
import { apiRequest } from '../../../services/api.js'
import { useRequest, useResource } from '../../../hooks/useApi.js'
import { useNwisResource } from '../hooks.js'
import { adaptAdvisoryList, adaptAuditList, adaptEventList } from '../adapters.js'
import { auditLabel, fmtM, fmtPct, hazardLabel, humanize, isNwisAudit, listOf, paths, safeDetails } from '../nwisModel.js'
import { useNwis } from '../NwisContext.jsx'
import { DrillingEventChip, NwisState, SyntheticDataBadge } from '../components.jsx'
import { EventCard } from './IntelligencePages.jsx'
import { Panel } from './OverviewPages.jsx'

// ── Advisories: engineer review of evidence-backed advisory text. Nothing here commands equipment. ──
const DECISIONS = [
  ['acknowledge', 'Acknowledge', 'I have seen this advisory and its evidence.'],
  ['review', 'Mark reviewed', 'Evidence reviewed; outcome recorded in the note.'],
  ['insufficient_evidence', 'Insufficient evidence', 'The cited evidence does not support this advisory.'],
  ['note', 'Add engineering note', 'Note only; status unchanged.'],
]
const FEEDBACK = [['useful', 'Useful'], ['already_known', 'Already known'], ['false_positive', 'False positive'], ['insufficient_evidence', 'Insufficient evidence']]

function AdvisoryReview({ advisory, onDone }) {
  const [decision, setDecision] = useState('acknowledge')
  const [feedback, setFeedback] = useState('useful')
  const [note, setNote] = useState('')
  const submit = useRequest()
  const valid = note.trim().length >= 5
  async function send(event) {
    event.preventDefault()
    if (!valid) return
    const result = await submit.run(paths.advisoryReview(advisory.id), { method: 'POST', body: { decision, feedback, note: note.trim() }, timeout: 20000 })
    if (result) { setNote(''); onDone() }
  }
  return <form className="nw-review" onSubmit={send} aria-labelledby="review-h">
    <h3 id="review-h">Engineer review</h3>
    <fieldset disabled={submit.loading}><legend className="visually-hidden">Decision</legend>
      <div className="nw-decisions">{DECISIONS.map(([value, label, hint]) => <label key={value} className="nw-decision"><input type="radio" name="decision" value={value} checked={decision === value} onChange={() => setDecision(value)} /><span><strong>{label}</strong><small>{hint}</small></span></label>)}</div>
      <label>Feedback for later evaluation<select value={feedback} onChange={e => setFeedback(e.target.value)}>{FEEDBACK.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label>Engineering note (required)<textarea rows={3} value={note} onChange={e => setNote(e.target.value)} maxLength={2000} aria-invalid={note.length > 0 && !valid} aria-describedby="note-hint" required /></label>
      <p id="note-hint" className="muted small">A reason is required so the decision is auditable. Reviewer identity and time come from your server session.</p>
      <button className="primary" disabled={!valid || submit.loading}>{submit.loading ? 'Recording…' : 'Record review'}</button>
    </fieldset>
    {submit.error && <p className="api-error" role="alert">{submit.error.status === 403 ? 'Your role cannot review advisories. ' : ''}{submit.error.message}</p>}
    {submit.data && <p className="result-status" role="status">Recorded. An audit entry was created. <Link to="/app/audit">View audit</Link></p>}
    <p className="nw-advisory-note"><Icon name="shield" size={16} />Recording a review never changes mud programs, drilling parameters, well-control settings or rig equipment.</p>
  </form>
}

function AdvisoryDetail({ advisory, onDone }) {
  const evidence = useNwisResource(advisory.evidence_ids.length ? paths.events({ ids: advisory.evidence_ids.join(',') }) : null, adaptEventList)
  const interval = advisory.interval_md_m
  return <article className="nw-advisory" aria-labelledby="adv-h">
    <header><p className="nw-eyebrow">{advisory.id} · {advisory.well_id}</p><h2 id="adv-h">{hazardLabel(advisory.hazard)}</h2>
      <p><span className="nw-status" data-status={advisory.status}>{humanize(advisory.status)}</span> <SyntheticDataBadge data={advisory} /></p></header>
    <dl className="nw-kpis is-tight">
      <div className="nw-kpi"><dt>Active interval</dt><dd>{interval ? `${fmtM(interval.top)} → ${fmtM(interval.base)} MD` : '—'}</dd><p className="muted small">{advisory.formation || ''}</p></div>
      <div className="nw-kpi"><dt>Inferred probability</dt><dd>{fmtPct(advisory.probability)}</dd></div>
      <div className="nw-kpi"><dt>Confidence</dt><dd>{fmtPct(advisory.confidence)}</dd></div>
    </dl>
    <section><h3>Observed facts · supporting evidence</h3>
      <NwisState request={evidence} what="supporting evidence" empty={!advisory.evidence_ids?.length ? 'No evidence linked to this advisory' : undefined} />
      <div className="nw-event-grid is-single">{listOf(evidence.data).map(e => <EventCard key={e.id} event={e} />)}</div></section>
    <section><h3>Historical response in offsets</h3>{advisory.historical_response?.length ? <ul>{advisory.historical_response.map(r => <li key={r}>{r}</li>)}</ul> : <p className="muted">None recorded.</p>}</section>
    <section className="nw-summary"><h3>NWIS advisory summary</h3><p>{advisory.summary || 'No summary generated.'}</p><p className="muted small">Generated route: {advisory.model_route || 'not reported'}. Advisory text only; the engineer decides.</p></section>
    <section><h3>Review history</h3>{advisory.reviews?.length ? <ol className="nw-history">{advisory.reviews.map((r, i) => <li key={i}><strong>{humanize(r.decision)}</strong> · {r.reviewer} · {r.at ? new Date(r.at).toLocaleString() : ''}{r.feedback && <span className="nw-badge">{humanize(r.feedback)}</span>}<p>{r.note}</p></li>)}</ol> : <p className="muted">Not yet reviewed.</p>}</section>
    <AdvisoryReview advisory={advisory} onDone={onDone} />
  </article>
}

export function AdvisoriesPage() {
  const { wellId } = useNwis()
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState('')
  const advisories = useNwisResource(paths.advisories({ well_id: wellId || undefined, status: status || undefined }), adaptAdvisoryList)
  const list = listOf(advisories.data)
  const selected = list.find(a => a.id === params.get('id')) || list[0] || null
  return <>
    <PageHeader title="Advisories" description="Evidence-backed advisories for engineer review. Acknowledge, review, mark insufficient evidence or add a note; every decision is audited. Advisory only." />
    <div className="nw-filters"><label>Status<select value={status} onChange={e => setStatus(e.target.value)}><option value="">All</option>{['open', 'acknowledged', 'reviewed', 'insufficient_evidence'].map(s => <option key={s} value={s}>{humanize(s)}</option>)}</select></label></div>
    <NwisState request={advisories} what="advisories" empty={advisories.data && !list.length ? 'No advisories for this well' : undefined} />
    {list.length > 0 && <div className="nw-desk">
      <nav className="panel nw-panel nw-adv-list" aria-label="Advisory queue"><ul>{list.map(a => <li key={a.id}>
        <button type="button" aria-current={a.id === selected?.id || undefined} onClick={() => setParams({ id: a.id })}>
          <DrillingEventChip type={a.hazard} /><span className="nw-status" data-status={a.status}>{humanize(a.status)}</span>
          <span className="muted small">{a.id} · {fmtPct(a.probability)} · {a.created_at ? new Date(a.created_at).toLocaleTimeString() : ''}</span></button></li>)}</ul></nav>
      <div className="panel nw-panel">{selected && <AdvisoryDetail key={selected.id} advisory={selected} onDone={advisories.refresh} />}</div>
    </div>}
  </>
}

// ── Audit: existing tamper-evident chain, with NWIS event types made readable. Paths and secrets are never shown. ──
export function NwisAuditPage() {
  const log = useNwisResource(paths.audit(), adaptAuditList)
  const verify = useResource('/audit/verify')
  const all = listOf(log.data)
  const hasNwis = all.some(e => isNwisAudit(e.event_type))
  const [onlyNwis, setOnlyNwis] = useState(true)
  const rows = onlyNwis && hasNwis ? all.filter(e => isNwisAudit(e.event_type)) : all
  return <>
    <PageHeader title="Audit" description="Every ingestion, extraction, offset query, risk assessment, alert and review is recorded on the tamper-evident chain. Tamper-evident, not tamper-proof." actions={<button type="button" onClick={() => { log.refresh(); verify.refresh() }}>Refresh</button>} />
    <section className="panel nw-panel"><div className="section-heading"><h2>Chain verification</h2></div>
      <NwisState request={verify} what="chain verification" />
      {verify.data && <p className={verify.data.valid ? 'result-status' : 'api-error'}>{verify.data.valid ? 'Chain verified' : 'Chain verification FAILED'}{verify.data.events_checked != null ? ` · ${verify.data.events_checked} events checked` : ''}{verify.data.note ? ` · ${verify.data.note}` : ''}</p>}
    </section>
    <section className="panel nw-panel"><div className="section-heading"><h2>Latest events</h2>
      {hasNwis && <label className="nw-inline-check"><input type="checkbox" checked={onlyNwis} onChange={e => setOnlyNwis(e.target.checked)} />NWIS events only</label>}</div>
      <NwisState request={log} what="the audit log" empty={log.data && !rows.length ? 'No audit events recorded yet' : undefined} />
      {rows.length > 0 && <ol className="nw-audit">{rows.map(e => <li key={e.id ?? e.sequence_number}>
        <span className="nw-audit-seq">#{e.sequence_number}</span>
        <div><strong>{auditLabel(e.event_type)}</strong> <span className="muted small">{e.occurred_at ? new Date(e.occurred_at).toLocaleString() : ''} · {e.actor_id || e.actor_kind || 'system'}</span>
          <dl className="nw-audit-details">{safeDetails(e.details || e.payload).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div></li>)}</ol>}
    </section>
  </>
}

// ── Help & resources ──
const DEMO = [
  ['Dashboard', '/app/dashboard', 'Select the active demo well and read its current depth, formation and hazard look-ahead.'],
  ['Nearby wells map', '/app/map', 'Set the radius (2 / 5 / 10 / 20 km) and see which offsets the backend returns.'],
  ['Offset analysis', '/app/offset-analysis', 'Explain why formation-matched wells outrank the closest well, using component scores.'],
  ['Formation correlation', '/app/correlation', 'Align formations by TVD and reveal historical stuck-pipe and loss events at the equivalent interval.'],
  ['Risk look-ahead', '/app/risk', 'Look ahead 100 m and open "Why this alert?" to cite the DDR/WCR passage.'],
  ['Live drilling', '/app/live', 'Show the simulated replay trend that reinforces or reduces the risk.'],
  ['Advisories', '/app/advisories', 'Acknowledge the advisory with an engineering note.'],
  ['Audit', '/app/audit', 'Show the audit entry created by the acknowledgement.'],
]
const GLOSSARY = [['eRTMAC', 'Oil India real-time monitoring and analytics centre for drilling'], ['NWIS', 'Nearby Wells Intelligence System'], ['Offset well', 'Historical nearby well used as an analog'],
  ['MD / TVD / TVDSS', 'Measured depth along the path / true vertical depth / TVD below sea-level datum'], ['WCR / DDR', 'Well Completion Report / Daily Drilling Report'], ['NPT', 'Non-productive time'],
  ['ROP / WOB / SPP', 'Rate of penetration / weight on bit / standpipe pressure'], ['WITSML / ETP', 'Energistics well-data standard and its transfer protocol']]
const PROBES = [['Wells', () => paths.wells({ limit: 1 })], ['Nearby', w => w && paths.nearby(w, { radius_km: 5 })], ['Correlation', w => w && paths.correlation(w)], ['Events', () => paths.events({ limit: 1 })],
  ['Risk', w => w && paths.risk(w, 100)], ['Telemetry', w => w && paths.telemetry(w, { window_s: 60 })], ['Advisories', () => paths.advisories()], ['Audit', () => paths.audit({ limit: 1 })]]

function IntegrationStatus() {
  const { wellId } = useNwis()
  const [results, setResults] = useState({})
  useEffect(() => {
    const controller = new AbortController()
    PROBES.forEach(([name, build]) => {
      const path = build(wellId)
      if (!path) return
      apiRequest(path, { signal: controller.signal, timeout: 8000 })
        .then(() => setResults(r => ({ ...r, [name]: 'available' })))
        .catch(error => { if (!controller.signal.aborted) setResults(r => ({ ...r, [name]: error.status ? `HTTP ${error.status}` : 'unreachable' })) })
    })
    return () => controller.abort()
  }, [wellId])
  return <div className="table-scroll" tabIndex={0} role="region" aria-label="NWIS API status"><table><thead><tr><th>Endpoint family</th><th>Status</th></tr></thead>
    <tbody>{PROBES.map(([name, build]) => <tr key={name}><td>{name} <code className="small">{build(wellId) || 'needs an active well'}</code></td><td><span className="nw-status" data-status={results[name] === 'available' ? 'fresh' : results[name] ? 'stale' : 'unknown'}>{results[name] || 'checking…'}</span></td></tr>)}</tbody></table></div>
}

export function HelpPage() {
  return <>
    <PageHeader title="Help & resources" description="How to use eRTMAC-NWIS, the judge demo flow, terminology and the data disclosure." />
    <div className="nw-dash-grid">
      <Panel title="What NWIS is"><p><strong>eRTMAC sees the live well. NWIS remembers nearby wells.</strong> NWIS is an offset-well knowledge and decision-support layer: it finds analogous nearby wells, aligns them by formation and depth, surfaces what happened at the equivalent interval and turns that history into hazard-specific look-ahead with cited evidence.</p>
        <p className="muted">It is not a rig-control system, not a replacement for eRTMAC and not a chatbot. Designed for Oil India / eRTMAC workflows; not deployed at Oil India.</p></Panel>
      <Panel title="Data disclosure"><p>The demo corpus is a clearly labelled <strong>synthetic demo dataset</strong> (<code>dataset_origin = synthetic_demo</code>). It proves the data model and workflows; it is not Oil India data. Telemetry is simulated replay unless a screen explicitly says LIVE.</p>
        <p className="muted small">Business impact figures such as NPT reduction are future validation KPIs, not claims.</p></Panel>
    </div>
    <Panel title="Judge demo flow (about 3 minutes)"><ol className="nw-demo">{DEMO.map(([name, to, text]) => <li key={to}><Link to={to}><strong>{name}</strong></Link><span>{text}</span></li>)}</ol></Panel>
    <div className="nw-dash-grid">
      <Panel title="Glossary"><dl className="nw-glossary">{GLOSSARY.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}</dl></Panel>
      <Panel title="NWIS API status"><p className="muted small">Live probe of the backend contract from this browser session.</p><IntegrationStatus /></Panel>
    </div>
    <Panel title="Safety scope"><p>Alerts and advisories are decision support. They never change mud programs, drilling parameters, well-control settings or rig equipment, and they require engineering review and OIL-specific validation before operational use.</p></Panel>
  </>
}
