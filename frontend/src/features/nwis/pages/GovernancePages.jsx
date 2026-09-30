import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AgentAvatar, Icon, PageHeader } from '../../../components/ui.jsx'
import { apiRequest } from '../../../services/api.js'
import { useRequest, useResource } from '../../../hooks/useApi.js'
import { useNwisResource } from '../hooks.js'
import { adaptAdvisoryList, adaptAssessment, adaptAuditList } from '../adapters.js'
import { auditLabel, personLabel, fmtM, fmtPct, hazardLabel, humanize, listOf, paths, safeDetails } from '../nwisModel.js'
import { useNwis } from '../NwisContext.jsx'
import { useSession } from '../../../app/session.jsx'
import { NwisState, SyntheticDataBadge } from '../components.jsx'
import { EventCard } from './IntelligencePages.jsx'
import { Panel } from './OverviewPages.jsx'

// ── Advisories: engineer review of evidence-backed advisory text. Nothing here commands equipment. ──
// B2 review body is { status, reason }; a pending advisory can be reviewed once (409 afterwards).
const DECISIONS = [
  ['acknowledged', 'Acknowledge', 'I have seen this advisory and its evidence.'],
  ['reviewed', 'Mark reviewed', 'Evidence reviewed; outcome recorded in the reason.'],
  ['dismissed', 'Insufficient evidence / dismiss', 'The cited evidence does not support this advisory.'],
]
const STATUSES = ['pending_review', 'acknowledged', 'reviewed', 'dismissed']

function AdvisoryReview({ advisory, onDone }) {
  const [status, setStatus] = useState('acknowledged')
  const [reason, setReason] = useState('')
  const submit = useRequest()
  const valid = reason.trim().length >= 5
  async function send(event) {
    event.preventDefault()
    if (!valid) return
    const result = await submit.run(paths.advisoryReview(advisory.id), { method: 'POST', body: { status, reason: reason.trim() }, timeout: 20000 })
    if (result) { setReason(''); onDone() }
  }
  return <form className="nw-review" onSubmit={send} aria-labelledby="review-h">
    <h3 id="review-h">Engineer review</h3>
    <fieldset disabled={submit.loading}><legend className="visually-hidden">Decision</legend>
      <div className="nw-decisions">{DECISIONS.map(([value, label, hint]) => <label key={value} className="nw-decision"><input type="radio" name="decision" value={value} checked={status === value} onChange={() => setStatus(value)} /><span><strong>{label}</strong><small>{hint}</small></span></label>)}</div>
      <label>Reason (required)<textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} aria-invalid={reason.length > 0 && !valid} aria-describedby="note-hint" required /></label>
      <p id="note-hint" className="muted small">At least 5 characters, so the decision is auditable. Reviewer identity and time come from your server session.</p>
      <button className="primary" disabled={!valid || submit.loading}>{submit.loading ? 'Recording…' : 'Record review'}</button>
    </fieldset>
    {submit.error && <p className="api-error" role="alert">{submit.error.status === 403 ? 'Your role cannot review advisories. ' : submit.error.status === 409 ? 'This advisory was already reviewed. ' : ''}{submit.error.message}</p>}
    <p className="nw-advisory-note"><Icon name="shield" size={16} />Recording a review never changes mud programs, drilling parameters, well-control settings or rig equipment.</p>
  </form>
}

function AdvisoryDetail({ advisory, onDone }) {
  const { user } = useSession()
  const assessment = useNwisResource(advisory.assessment_id ? paths.assessment(advisory.assessment_id) : null, adaptAssessment)
  const a = assessment.data
  const h = a?.hazard
  return <article className="nw-advisory" aria-labelledby="adv-h">
    <header><p className="nw-eyebrow" title={advisory.id}>Advisory {advisory.id.slice(0, 12)} · {a?.well_id || 'well —'}</p><h2 id="adv-h">{h ? hazardLabel(h.type) : 'Advisory'}</h2>
      <p><span className="nw-status" data-status={advisory.status}>{humanize(advisory.status)}</span> <SyntheticDataBadge data={advisory} /></p></header>
    <NwisState request={assessment} what="the linked assessment" />
    {a && <dl className="nw-kpis is-tight">
      <div className="nw-kpi"><dt>Assessed at</dt><dd>{fmtM(a.current_md_m)} MD</dd><p className="muted small">{[a.formation, a.lookahead_m != null ? `next ${a.lookahead_m} m` : null, a.as_of ? new Date(a.as_of).toLocaleString() : null].filter(Boolean).join(' · ')}</p></div>
      <div className="nw-kpi"><dt>Uncalibrated estimate</dt><dd>{h?.probability == null ? '—' : fmtPct(h.probability)}</dd></div>
      <div className="nw-kpi"><dt>Confidence</dt><dd>{fmtPct(h?.confidence)}</dd></div>
    </dl>}
    <section><h3>Observed facts · cited evidence</h3>
      {a && (a.evidence.length ? <div className="nw-event-grid is-single">{a.evidence.map(link => <EventCard key={link.event.id} event={link.event} />)}</div> : <p className="muted">The assessment cites no events.</p>)}</section>
    <section className="nw-summary"><h3 className="nw-agent-heading"><AgentAvatar size={24} />NWIS advisory</h3><p>{advisory.text || 'No advisory text.'}</p><p className="muted small">Generated route: {advisory.model_route || 'not reported'}. Advisory text only; the engineer decides.</p></section>
    {advisory.status === 'pending_review' ? <AdvisoryReview advisory={advisory} onDone={onDone} />
      : <section><h3>Review</h3><p><strong>{humanize(advisory.status)}</strong> · <span title={advisory.reviewer || undefined}>{personLabel(advisory.reviewer, user) || 'reviewer not recorded'}</span> · {advisory.reviewed_at ? new Date(advisory.reviewed_at).toLocaleString() : 'time not recorded'}</p>
        {advisory.reason && <p>{advisory.reason}</p>}<p className="small"><Link to="/app/audit">View audit</Link></p></section>}
  </article>
}

export function AdvisoriesPage() {
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState('')
  const advisories = useNwisResource(paths.advisories({ limit: 100 }), adaptAdvisoryList)
  const all = listOf(advisories.data)
  const list = status ? all.filter(a => a.status === status) : all // B2 has no status filter; one bounded page is filtered locally.
  const selected = list.find(a => a.id === params.get('id')) || list[0] || null
  return <>
    <PageHeader title="Advisories" description="Evidence-backed advisories for engineer review. Acknowledge, mark reviewed or dismiss for insufficient evidence; every decision is audited. Advisory only." />
    <div className="nw-filters"><label>Status<select value={status} onChange={e => setStatus(e.target.value)}><option value="">All</option>{STATUSES.map(s => <option key={s} value={s}>{humanize(s)}</option>)}</select></label></div>
    <NwisState request={advisories} what="advisories" empty={advisories.data && !list.length ? (all.length ? 'No advisories with this status' : 'No advisories yet. They are raised after successive assessments show a sustained risk.') : undefined} />
    {list.length > 0 && <div className="nw-desk">
      <nav className="panel nw-panel nw-adv-list" aria-label="Advisory queue"><ul>{list.map(a => <li key={a.id}>
        <button type="button" aria-current={a.id === selected?.id || undefined} onClick={() => setParams({ id: a.id })}>
          <strong title={a.id}>{a.id.slice(0, 12)}</strong><span className="nw-status" data-status={a.status}>{humanize(a.status)}</span>
          <span className="muted small">{a.created_at ? new Date(a.created_at).toLocaleString() : ''}</span>
          {a.text && <span className="small nw-alert-text">{a.text.slice(0, 120)}{a.text.length > 120 ? '…' : ''}</span>}</button></li>)}</ul></nav>
      <div className="panel nw-panel">{selected && <AdvisoryDetail key={selected.id} advisory={selected} onDone={advisories.refresh} />}</div>
    </div>}
  </>
}

// ── Audit: GET /api/audit (NWIS entries; non-admins see their own) and the chain check at /audit/verify. ──
export function NwisAuditPage() {
  const { user } = useSession()
  const log = useNwisResource(paths.audit(), adaptAuditList)
  const verify = useResource(paths.auditVerify)
  const rows = listOf(log.data)
  return <>
    <PageHeader title="Audit" description="Terms acceptance, risk assessments, knowledge queries, report ingestion and advisory reviews are recorded on the hash-chained audit log. Tamper-evident, not tamper-proof." actions={<button type="button" onClick={() => { log.refresh(); verify.refresh() }}>Refresh</button>} />
    <section className="panel nw-panel"><div className="section-heading"><h2>Chain verification</h2></div>
      <NwisState request={verify} what="chain verification" />
      {verify.data && <p className={verify.data.valid ? 'result-status' : 'api-error'}>{verify.data.valid ? 'Chain verified' : 'Chain verification FAILED'}{verify.data.events_checked != null ? ` · ${verify.data.events_checked} events checked` : ''}</p>}
    </section>
    <section className="panel nw-panel"><div className="section-heading"><h2>Latest events</h2></div>
      <NwisState request={log} what="the audit log" empty={log.data && !rows.length ? 'No audit events recorded yet' : undefined} />
      {rows.length > 0 && <ol className="nw-audit">{rows.map(e => <li key={e.id ?? e.sequence_number}>
        <span className="nw-audit-seq">#{e.sequence_number}</span>
        <div><strong>{auditLabel(e.event_type)}</strong> <span className="muted small">{e.occurred_at ? new Date(e.occurred_at).toLocaleString() : ''} · <span title={e.actor_id || undefined}>{personLabel(e.actor_id, user) || e.actor_kind || 'system'}</span></span>
          <dl className="nw-audit-details">{safeDetails(e.details).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div></li>)}</ol>}
    </section>
  </>
}

// ── Help & resources ──
const DEMO = [
  ['Dashboard', '/app/dashboard', 'Select the active demo well and read its current depth, formation and hazard look-ahead.'],
  ['Nearby wells map', '/app/map', 'Set the radius (2 / 5 / 10 / 20 km) and see which offsets the backend returns.'],
  ['Offset analysis', '/app/offset-analysis', 'Explain why formation-matched wells outrank the closest well, using component scores.'],
  ['Formation correlation', '/app/correlation', 'Align formations by depth (TVDSS where available) and reveal historical stuck-pipe and loss events at the equivalent interval.'],
  ['Risk look-ahead', '/app/risk', 'Look ahead 100 m and open "Why this alert?" to cite the DDR/WCR passage.'],
  ['Live drilling', '/app/live', 'Show the simulated replay trend that reinforces or reduces the risk.'],
  ['Advisories', '/app/advisories', 'Acknowledge the advisory with a review reason.'],
  ['Audit', '/app/audit', 'Show the audit entry created by the acknowledgement.'],
]
const GLOSSARY = [['eRTMAC', 'Oil India real-time monitoring and analytics centre for drilling'], ['NWIS', 'Nearby Wells Intelligence System'], ['Offset well', 'Historical nearby well used as an analog'],
  ['MD / TVD / TVDSS', 'Measured depth along the path / true vertical depth / TVD below sea-level datum'], ['WCR / DDR', 'Well Completion Report / Daily Drilling Report'], ['NPT', 'Non-productive time'],
  ['ROP / WOB / SPP', 'Rate of penetration / weight on bit / standpipe pressure'], ['WITSML / ETP', 'Energistics well-data standard and its transfer protocol']]
const PROBES = [['Wells', () => paths.wells({ limit: 1 })], ['Nearby', w => w && paths.nearby(w, { radius_km: 5 })], ['Correlation', w => w && paths.correlation(w)], ['Events', () => paths.events({ limit: 1 })],
  ['Risk', w => w && paths.risk(w, 100)], ['Telemetry', w => w && paths.telemetry(w, { limit: 1 })], ['Advisories', () => paths.advisories()], ['Audit', () => paths.audit({ limit: 1 })]]

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
