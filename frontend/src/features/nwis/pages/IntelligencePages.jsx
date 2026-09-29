import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Icon, PageHeader } from '../../../components/ui.jsx'
import { TimeSeriesChart } from '../../../components/charts.jsx'
import { useRequest, useResource } from '../../../hooks/useApi.js'
import { HAZARDS, LOOKAHEAD_M, PRIMARY_HAZARDS, fmtAge, fmtM, fmtPct, freshness, groupResults, hazardLabel, humanize, listOf, normalizeHazard, paths, riskLevel, telemetrySeries } from '../nwisModel.js'
import { useNwis } from '../NwisContext.jsx'
import { useNearby, useNow, usePolling, useRisk } from '../hooks.js'
import { DrillingEventChip, EvidenceDrawer, NwisState, RiskCard, SyntheticDataBadge, VerificationBadge, WellContextBar } from '../components.jsx'
import { Panel } from './OverviewPages.jsx'

// ── Drilling events ──
export function EventCard({ event: e }) {
  return <article className="nw-event-card">
    <header><DrillingEventChip type={e.type} severity={e.severity} /><strong><Link to={`/app/wells/${encodeURIComponent(e.well_id)}`}>{e.well_id}</Link></strong>
      <span>{fmtM(e.depth_md_m)} MD · {fmtM(e.depth_tvd_m)} TVD</span><span>{e.formation || 'Formation unknown'}</span><VerificationBadge state={e.verification} /></header>
    <p className="nw-raw-label">Original observation (source wording)</p>
    <blockquote>“{e.raw_observation || 'No source wording stored.'}”</blockquote>
    <dl className="nw-event-facts">
      <div><dt>Normalized type</dt><dd><code>{e.type}</code></dd></div>
      <div><dt>Severity</dt><dd>{humanize(e.severity) || '—'}</dd></div>
      <div><dt>Mitigation</dt><dd>{e.mitigation || '—'}</dd></div>
      <div><dt>Outcome</dt><dd>{e.outcome || '—'}</dd></div>
      <div><dt>NPT</dt><dd>{e.npt_hours != null ? `${e.npt_hours} h` : '—'}</dd></div>
      <div><dt>Extraction confidence</dt><dd>{fmtPct(e.confidence)}</dd></div>
    </dl>
    <p className="nw-cite"><Icon name="book" size={14} />{e.source?.title || 'Source'} · <strong>{e.source?.report_id || 'report not linked'}</strong> · page {e.source?.page ?? '—'}</p>
  </article>
}

export function EventsPage() {
  const { wellList } = useNwis()
  const [params, setParams] = useSearchParams()
  const [f, setF] = useState({ well_id: params.get('well') || '', formation: '', type: '', severity: '', depth_min: '', depth_max: '' })
  const events = useResource(paths.events({ ...f, limit: 100 }))
  const list = listOf(events.data)
  const formations = [...new Set(wellList.flatMap(w => (w.formations || []).map(x => x.name)))]
  const update = (key, value) => { setF(current => ({ ...current, [key]: value })); if (key === 'well_id') setParams(value ? { well: value } : {}, { replace: true }) }
  return <>
    <PageHeader title="Drilling events" description="Historical events extracted from WCR/DDR reports. The source wording is preserved next to every normalized field, with report and page." />
    <form className="nw-filters" onSubmit={event => event.preventDefault()} aria-label="Event filters">
      <label>Well<select value={f.well_id} onChange={e => update('well_id', e.target.value)}><option value="">All wells</option>{wellList.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <label>Formation<select value={f.formation} onChange={e => update('formation', e.target.value)}><option value="">Any</option>{formations.map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Event type<select value={f.type} onChange={e => update('type', e.target.value)}><option value="">Any</option>{Object.entries(HAZARDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>Severity<select value={f.severity} onChange={e => update('severity', e.target.value)}><option value="">Any</option>{['low', 'moderate', 'high'].map(s => <option key={s} value={s}>{humanize(s)}</option>)}</select></label>
      <label>TVD from (m)<input type="number" inputMode="numeric" min="0" value={f.depth_min} onChange={e => update('depth_min', e.target.value)} /></label>
      <label>TVD to (m)<input type="number" inputMode="numeric" min="0" value={f.depth_max} onChange={e => update('depth_max', e.target.value)} /></label>
    </form>
    <Panel title={events.data ? `${events.data.total ?? list.length} events${(events.data.total ?? 0) > list.length ? ` (showing ${list.length})` : ''}` : 'Events'} data={events.data}>
      <NwisState request={events} what="drilling events" empty={events.data && !list.length ? 'No events match these filters' : undefined} />
      <div className="nw-event-grid">{list.map(e => <EventCard key={e.id} event={e} />)}</div>
    </Panel>
  </>
}

// ── Risk look-ahead (flagship) ──
function LookaheadProfile({ wellId }) {
  const r50 = useResource(wellId ? paths.risk(wellId, 50) : null)
  const r100 = useResource(wellId ? paths.risk(wellId, 100) : null)
  const r150 = useResource(wellId ? paths.risk(wellId, 150) : null)
  const all = [r50, r100, r150]
  if (all.some(r => !r.data)) return all.some(r => r.error) ? <p className="muted small">Look-ahead profile unavailable.</p> : null
  const byWindow = all.map(r => Object.fromEntries((r.data.hazards || []).map(normalizeHazard).map(h => [h.type, h])))
  const types = PRIMARY_HAZARDS.filter(t => byWindow.some(w => w[t]))
  return <div className="table-scroll" tabIndex={0} role="region" aria-label="Risk by look-ahead distance"><table className="nw-profile">
    <caption>Probability (confidence) by look-ahead distance</caption>
    <thead><tr><th scope="col">Hazard</th>{LOOKAHEAD_M.map(m => <th key={m} scope="col">Next {m} m</th>)}</tr></thead>
    <tbody>{types.map(t => <tr key={t}><th scope="row">{hazardLabel(t)}</th>{byWindow.map((w, i) => <td key={i} className="num" data-level={w[t] ? riskLevel(w[t]) : undefined}>
      {w[t] ? <>{fmtPct(w[t].probability)} <small>({fmtPct(w[t].confidence)})</small></> : '—'}</td>)}</tr>)}</tbody></table></div>
}

export function RiskPage() {
  const { well, wellId, lookahead } = useNwis()
  const risk = useRisk()
  const nearby = useNearby({ radiusKm: 20 })
  const [why, setWhy] = useState(null)
  const d = risk.request.data
  const ordered = PRIMARY_HAZARDS.map(t => risk.hazards.find(h => h.type === t)).filter(Boolean).concat(risk.hazards.filter(h => !PRIMARY_HAZARDS.includes(h.type)))
  return <>
    <PageHeader title="Risk look-ahead" description="Hazard-specific risk for the interval ahead of the bit, from matched offset history and live telemetry. There is no single overall AI risk: each hazard stands on its own evidence." />
    <WellContextBar lookahead />
    <section className="nw-interval" aria-label="Assessed interval">
      <div><span className="nw-eyebrow">Assessed interval</span><strong>{d?.window_md_m ? `${fmtM(d.window_md_m.top)} → ${fmtM(d.window_md_m.base)} MD` : well?.current_md_m != null ? `${fmtM(well.current_md_m)} → ${fmtM(well.current_md_m + lookahead)} MD` : `Next ${lookahead} m`}</strong></div>
      <div><span className="nw-eyebrow">Formation at bit</span><strong>{d?.formation || well?.current_formation || '—'}</strong></div>
      <div><span className="nw-eyebrow">Assessment</span><strong>{d?.as_of ? new Date(d.as_of).toLocaleTimeString() : '—'}</strong><span className="muted small">{d?.model_version || ''}</span></div>
      <SyntheticDataBadge data={d} />
    </section>
    <NwisState request={risk.request} what="the risk look-ahead" empty={d && !ordered.length ? 'No hazards assessed for this interval' : undefined} />
    {ordered.length > 0 && <div className="nw-risk-grid">{ordered.map(h => <RiskCard key={h.type} hazard={h} lookahead={lookahead} onWhy={setWhy} />)}</div>}
    <Panel title="How risk changes ahead of the bit" data={d}><LookaheadProfile wellId={wellId} /></Panel>
    <p className="nw-advisory-note"><Icon name="shield" size={16} />Advisory decision support. NWIS never changes mud programs, drilling parameters, well-control settings or rig equipment. Acknowledge or review alerts in <Link to="/app/advisories">Advisories</Link>.</p>
    <EvidenceDrawer hazard={why} risk={d} offsets={nearby.offsets} onClose={() => setWhy(null)} />
  </>
}

// ── Live drilling (replay) ──
const COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)']
export function LivePage() {
  const { wellId } = useNwis()
  const telemetry = useResource(wellId ? paths.telemetry(wellId, { window_s: 7200 }) : null)
  const [last, setLast] = useState(null)
  if (telemetry.data && telemetry.data !== last) setLast(telemetry.data) // keep the previous frame while refreshing
  usePolling(telemetry.refresh, 15000)
  const data = telemetry.data || last
  const series = telemetrySeries(data)
  const missing = (data?.channels || []).filter(c => !series.some(s => s.id === c.mnemonic))
  const now = useNow(5000)
  const fresh = freshness(data?.as_of, now, data?.stale_after_s || 120)
  const live = data?.mode === 'live'
  const depth = series.length ? series[0].points.filter(p => p.md != null).map(p => ({ t: p.t, v: p.md })) : []
  return <>
    <PageHeader title="Live drilling" description="Depth- and time-synchronized drilling parameters for the active well. Channels are shown only when the backend provides values." />
    <WellContextBar />
    {data && <section className="nw-live-banner" data-mode={live ? 'live' : 'replay'} data-fresh={fresh.state} role="status">
      <strong>{live ? 'LIVE FEED' : 'SIMULATED / REPLAY DATA'}</strong>
      <span>{live ? `Source: ${data.source || 'unspecified'}` : `Source: ${data.source || 'replay'}. Not an Oil India or eRTMAC live feed.`}</span>
      <span>Adapter: {data.adapter || 'WITSML / ETP-ready adapter (not connected)'}</span>
      <span className="nw-status" data-status={fresh.state}>{fresh.state === 'stale' ? `STALE · last sample ${fmtAge(fresh.ageS)} · values are not current` : `Last sample ${fmtAge(fresh.ageS)}`}</span>
      <SyntheticDataBadge data={data} />
    </section>}
    {telemetry.error && last && <p className="api-error" role="alert">Refresh failed: {telemetry.error.message}. Showing the last received frame; it is not current.</p>}
    {!data && <NwisState request={telemetry} what="telemetry" />}
    {data && <>
      {depth.length > 1 && <Panel title="Bit depth (MD) over time"><TimeSeriesChart series={[{ id: 'md', label: 'MD', color: 'var(--chart-2)', points: depth }]} unit="m" height={170} label="Measured depth over time" /></Panel>}
      <div className="nw-live-grid">{series.map((s, i) => <section key={s.id} className="panel nw-panel nw-live-chart" aria-labelledby={`ch-${s.id}`}>
        <div className="section-heading"><h2 id={`ch-${s.id}`}>{s.label}</h2><span className="nw-panel-meta"><strong className="nw-live-value">{s.points.at(-1).v} {s.unit}</strong>{s.quality && s.quality !== 'ok' && <span className="nw-badge">{s.quality}</span>}</span></div>
        <TimeSeriesChart series={[{ ...s, color: COLORS[i % COLORS.length] }]} unit={s.unit} height={170} label={`${s.label} (${s.unit})`} /></section>)}</div>
      {missing.length > 0 && <p className="muted small">Declared without values (not drawn): {missing.map(c => `${c.label || c.mnemonic}${c.quality ? ` (${c.quality})` : ''}`).join(', ')}.</p>}
    </>}
  </>
}

// ── Knowledge search ──
const EXAMPLES = [
  'Show stuck-pipe incidents in Tipam between 2400-2700 m TVD',
  'What mitigations worked for mud loss near this active well?',
  'Compare casing issues in the most relevant offsets',
]
function ResultItem({ item }) {
  const depth = item.depth_tvd_m != null ? `${fmtM(item.depth_tvd_m)} TVD` : item.depth_md_m != null ? `${fmtM(item.depth_md_m)} MD` : null
  const page = item.page ?? item.source?.page
  return <li className="nw-result">
    <header><strong>{item.title || item.event_id || item.report_id || item.well_id}</strong>
      <VerificationBadge state={item.verification} />{item.confidence != null && <span className="nw-badge">confidence {fmtPct(item.confidence)}</span>}</header>
    {item.excerpt && <blockquote>“{item.excerpt}”</blockquote>}
    {item.mitigation && <p className="small"><strong>Mitigation:</strong> {item.mitigation}</p>}
    <p className="nw-cite"><Icon name="book" size={14} />{[item.source?.report_id || item.report_id, page != null ? `page ${page}` : null, item.well_id, depth, item.formation].filter(Boolean).join(' · ') || 'No source metadata returned'}</p>
  </li>
}

export function KnowledgeSearchPage() {
  const { wellId } = useNwis()
  const [query, setQuery] = useState('')
  const [scoped, setScoped] = useState(true)
  const search = useRequest()
  const groups = groupResults(search.data)
  const total = groups.well.length + groups.event.length + groups.report.length
  const run = text => search.run(paths.query, { method: 'POST', timeout: 120000, body: { query: text, well_id: scoped ? wellId : undefined, mode: 'nwis_evidence', request_id: crypto.randomUUID() } })
  return <>
    <PageHeader title="Knowledge search" description="Search historical drilling evidence in natural language. Results are grouped by well, event and report, and every result carries its source, page, depth and formation." />
    <section className="panel nw-panel">
      <form onSubmit={event => { event.preventDefault(); if (query.trim()) run(query.trim()) }}>
        <label>Question or search<textarea rows={2} value={query} onChange={e => setQuery(e.target.value)} maxLength={1000} required placeholder="e.g. Show stuck-pipe incidents in Tipam between 2400-2700 m TVD" /></label>
        <label className="nw-inline-check"><input type="checkbox" checked={scoped} onChange={e => setScoped(e.target.checked)} />Prioritise offsets of the active well ({wellId || 'none'})</label>
        <button className="primary" disabled={search.loading || !query.trim()}>Search evidence</button>
      </form>
      <div className="nw-examples"><span className="muted small">Try:</span>{EXAMPLES.map(x => <button key={x} type="button" className="ghost" onClick={() => { setQuery(x); run(x) }}>{x}</button>)}</div>
    </section>
    <NwisState request={search} what="knowledge search" />
    {search.data && <>
      <p className="nw-result-summary">{total} results{search.data.mode ? ` · ${search.data.mode}` : ''} <SyntheticDataBadge data={search.data} /></p>
      {search.data.summary && <section className="panel nw-panel"><h2>Cited summary</h2><p>{search.data.summary}</p>{!search.data.citations?.length && <p className="api-error">No citations were returned with this summary; treat it as unsupported.</p>}</section>}
      {!total && <div className="state state-empty"><strong>No matching evidence</strong><p>NWIS returned no cited records. It will not answer without evidence.</p></div>}
      <div className="nw-result-groups">{[['well', 'Wells'], ['event', 'Events'], ['report', 'Reports']].map(([key, label]) => groups[key].length > 0 && <section key={key} className="panel nw-panel" aria-labelledby={`rg-${key}`}>
        <h2 id={`rg-${key}`}>{label} <span className="muted small">{groups[key].length}</span></h2><ul className="nw-results">{groups[key].map((item, i) => <ResultItem key={`${key}-${i}`} item={item} />)}</ul></section>)}</div>
    </>}
  </>
}
