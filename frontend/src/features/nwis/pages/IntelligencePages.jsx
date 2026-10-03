import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AgentAvatar, Icon, PageHeader } from '../../../components/ui.jsx'
import { TimeSeriesChart } from '../../../components/charts.jsx'
import { useRequest } from '../../../hooks/useApi.js'
import { EVENT_TYPES, LOOKAHEAD_M, PRIMARY_HAZARDS, fmtM, fmtPct, fmtValue, hazardLabel, humanize, listOf, paths, riskLevel } from '../nwisModel.js'
import { useNwis } from '../NwisContext.jsx'
import { useNearby, useNwisResource, usePolling, useRisk } from '../hooks.js'
import { adaptEventList, adaptFormationList, adaptQuery, adaptRisk, adaptTelemetry, groupResults } from '../adapters.js'
import { DrillingEventChip, EvidenceDrawer, NwisState, RiskCard, SyntheticDataBadge, VerificationBadge, WellContextBar } from '../components.jsx'
import { Panel } from './OverviewPages.jsx'
import { MODELS, buildMessages } from '../browserLlmModel.js'
import { askBrowserLlm, browserLlmSupported } from '../browserLlm.js'

// ── Drilling events ──
export function EventCard({ event: e }) {
  return <article className="nw-event-card">
    <header><DrillingEventChip type={e.type} severity={e.severity} /><strong><Link to={`/app/wells/${encodeURIComponent(e.well_id)}`}>{e.well_id}</Link></strong>
      <span>{fmtM(e.depth_md_m)} MD · {fmtM(e.depth_tvd_m)} TVD</span><span>{e.formation || 'Formation unknown'}</span><VerificationBadge state={e.verification} /></header>
    <p className="nw-raw-label">Source wording (as extracted)</p>
    <blockquote>“{e.raw_observation || 'No source wording stored.'}”</blockquote>
    {e.observation && e.observation !== e.raw_observation && <p className="small"><strong>Observation:</strong> {e.observation}</p>}
    <dl className="nw-event-facts">
      <div><dt>Normalized type</dt><dd><code>{e.type}</code></dd></div>
      <div><dt>Severity</dt><dd>{humanize(e.severity) || '—'}</dd></div>
      <div><dt>Mitigation</dt><dd>{e.mitigation || '—'}</dd></div>
      <div><dt>Outcome</dt><dd>{e.outcome || '—'}</dd></div>
      <div><dt>NPT</dt><dd>{e.npt_hours != null ? `${e.npt_hours} h` : '—'}</dd></div>
      <div><dt>Extraction confidence</dt><dd>{fmtPct(e.confidence)}</dd></div>
      <div><dt>TVDSS</dt><dd>{e.depth_tvdss_m == null ? 'Not recorded' : `${fmtM(e.depth_tvdss_m)}`}</dd></div>
    </dl>
    <p className="nw-cite"><Icon name="book" size={14} />{e.source?.url ? <a href={e.source.url} target="_blank" rel="noreferrer">{e.source.report_id} · page {e.source.page ?? '—'}</a> : <><strong>{e.source?.report_id || 'report not linked'}</strong> · page {e.source?.page ?? '—'}</>} · event <code>{e.id}</code></p>
  </article>
}

export function EventsPage() {
  const { wellList, wellId } = useNwis()
  const [params, setParams] = useSearchParams()
  const [f, setF] = useState({ well_id: params.get('well') || '', formation: '', type: '', depth_basis: 'tvd', depth_min: '', depth_max: '' })
  const events = useNwisResource(paths.events({ ...f, depth_basis: f.depth_min !== '' || f.depth_max !== '' ? f.depth_basis : undefined, limit: 100 }), adaptEventList)
  const list = listOf(events.data)
  const formationList = useNwisResource(wellId ? paths.formations(wellId) : null, adaptFormationList)
  const formations = [...new Set((formationList.data?.items ?? []).map(x => x.name).filter(Boolean))]
  const update = (key, value) => { setF(current => ({ ...current, [key]: value })); if (key === 'well_id') setParams(value ? { well: value } : {}, { replace: true }) }
  return <>
    <PageHeader title="Drilling events" description="Historical events extracted from WCR/DDR reports. The source wording is preserved next to every normalized field, with report and page." />
    <form className="nw-filters" onSubmit={event => event.preventDefault()} aria-label="Event filters">
      <label>Well<select value={f.well_id} onChange={e => update('well_id', e.target.value)}><option value="">All wells</option>{wellList.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <label>Formation<select value={f.formation} onChange={e => update('formation', e.target.value)}><option value="">Any</option>{formations.map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Event type<select value={f.type} onChange={e => update('type', e.target.value)}><option value="">Any</option>{EVENT_TYPES.map(k => <option key={k} value={k}>{hazardLabel(k)}</option>)}</select></label>
      <label>Depth basis<select value={f.depth_basis} onChange={e => update('depth_basis', e.target.value)}><option value="md">MD</option><option value="tvd">TVD</option><option value="tvdss">TVDSS</option></select></label>
      <label>From (m)<input type="number" inputMode="numeric" min={f.depth_basis === 'tvdss' ? undefined : 0} value={f.depth_min} onChange={e => update('depth_min', e.target.value)} /></label>
      <label>To (m)<input type="number" inputMode="numeric" min={f.depth_basis === 'tvdss' ? undefined : 0} value={f.depth_max} onChange={e => update('depth_max', e.target.value)} /></label>
    </form>
    <Panel title={events.data ? `${list.length} event${list.length === 1 ? '' : 's'}${events.data.has_more ? ' (first 100; narrow the filters for more)' : ''}` : 'Events'} data={events.data}>
      <NwisState request={events} what="drilling events" empty={events.data && !list.length ? 'No events match these filters' : undefined} />
      <div className="nw-event-grid">{list.map(e => <EventCard key={e.id} event={e} />)}</div>
    </Panel>
  </>
}

// ── Risk look-ahead (flagship) ──
function LookaheadProfile({ wellId }) {
  const r50 = useNwisResource(wellId ? paths.risk(wellId, 50) : null, adaptRisk)
  const r100 = useNwisResource(wellId ? paths.risk(wellId, 100) : null, adaptRisk)
  const r150 = useNwisResource(wellId ? paths.risk(wellId, 150) : null, adaptRisk)
  const all = [r50, r100, r150]
  if (all.some(r => !r.data)) return all.some(r => r.error) ? <p className="muted small">Look-ahead profile unavailable.</p> : null
  const byWindow = all.map(r => Object.fromEntries(r.data.hazards.map(h => [h.type, h])))
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
      <div><span className="nw-eyebrow">Formation at bit</span><strong>{d?.formation || '—'}</strong></div>
      <div><span className="nw-eyebrow">Assessment (replay time)</span><strong>{d?.as_of ? new Date(d.as_of).toLocaleString() : '—'}</strong><span className="muted small">{d?.model_version || ''}</span></div>
      {d && !d.calibrated && <span className="nw-badge nw-uncalibrated" title="Heuristic exposure score from matched offsets and a bounded telemetry modifier; not a validated field-event probability.">Uncalibrated estimate</span>}
      <SyntheticDataBadge data={d} />
    </section>
    <NwisState request={risk.request} what="the risk look-ahead" empty={d && !ordered.length ? 'No hazards assessed for this interval' : undefined} />
    {ordered.length > 0 && <div className="nw-risk-grid">{ordered.map(h => <RiskCard key={h.type} hazard={h} lookahead={lookahead} onWhy={setWhy} />)}</div>}
    <Panel title="How risk changes ahead of the bit" data={d}><LookaheadProfile wellId={wellId} /></Panel>
    <p className="nw-advisory-note"><Icon name="shield" size={16} />Advisory decision support. NWIS never changes mud programs, drilling parameters, well-control settings or rig equipment. Acknowledge or review alerts in <Link to="/app/advisories">Advisories</Link>.</p>
    <EvidenceDrawer hazard={why} risk={d} offsets={nearby.offsets} wellId={wellId} onRecorded={risk.request.refresh} onClose={() => setWhy(null)} />
  </>
}

// ── Live drilling (replay) ──
const COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)']
export function LivePage() {
  const { wellId } = useNwis()
  const telemetry = useNwisResource(wellId ? paths.telemetry(wellId, { limit: 1000 }) : null, adaptTelemetry)
  const [last, setLast] = useState(null)
  if (telemetry.data && telemetry.data !== last) setLast(telemetry.data) // keep the previous frame while refreshing
  usePolling(telemetry.refresh, 15000)
  const data = telemetry.data || last
  const series = data?.series ?? []
  const missing = data?.missing ?? []
  const fresh = { state: data?.state === 'fresh' ? 'fresh' : 'stale' }
  const live = data?.mode === 'live'
  const depth = (series.find(s => s.id === 'MD') ?? series[0])?.points.filter(p => p.md != null).map(p => ({ t: p.t, v: p.md })) ?? []
  return <>
    <PageHeader title="Live drilling" description="Depth- and time-synchronized drilling parameters for the active well. Channels are shown only when the backend provides values." />
    <WellContextBar />
    {data && <section className="nw-live-banner" data-mode={live ? 'live' : 'replay'} data-fresh={fresh.state} role="status">
      <strong>{live ? 'LIVE FEED' : 'SIMULATED / REPLAY DATA'}</strong>
      <span>{live ? `Source: ${data.source || 'unspecified'}` : `Source: ${data.source || 'replay'}. Not an Oil India or eRTMAC live feed.`}</span>
      <span>Adapter: {data.adapter || 'WITSML / ETP-ready adapter (not connected)'}</span>
      <span className="nw-status" data-status={fresh.state}>Channels {data.state} at replay time {data.as_of ? new Date(data.as_of).toLocaleString() : '—'}{data.state !== 'fresh' ? ' · some values are not current' : ''}</span>
      <SyntheticDataBadge data={data} />
    </section>}
    {telemetry.error && last && <p className="api-error" role="alert">Refresh failed: {telemetry.error.message}. Showing the last received frame; it is not current.</p>}
    {!data && <NwisState request={telemetry} what="telemetry" />}
    {data && <>
      {depth.length > 1 && <Panel title="Bit depth (MD) over time"><TimeSeriesChart series={[{ id: 'md', label: 'MD', color: 'var(--chart-2)', points: depth }]} unit="m" height={170} label="Measured depth over time" /></Panel>}
      <div className="nw-live-grid">{series.map((s, i) => <section key={s.id} className="panel nw-panel nw-live-chart" aria-labelledby={`ch-${s.id}`}>
        <div className="section-heading"><h2 id={`ch-${s.id}`}>{s.label}</h2><span className="nw-panel-meta"><strong className="nw-live-value">{fmtValue(s.points.at(-1).v)} {s.unit}</strong>{s.quality && <span className="nw-badge" data-state={s.quality}>{s.quality}</span>}</span></div>
        <TimeSeriesChart series={[{ ...s, color: COLORS[i % COLORS.length] }]} unit={s.unit} height={170} label={`${s.label} (${s.unit})`} /></section>)}</div>
      {missing.length > 0 && <p className="muted small">Declared without values (not drawn): {missing.map(c => `${c.label || c.mnemonic}${c.quality ? ` (${c.quality})` : ''}`).join(', ')}.</p>}
    </>}
  </>
}

// ── Knowledge search ──
const EXAMPLES = [
  'Show stuck-pipe incidents in Tipam between 2400-2700 m TVD',
  'What mitigations worked for mud losses near this active well?',
  'Compare events in the three most relevant offsets',
]
function ResultItem({ item }) {
  const depth = item.depth_tvd_m != null ? `${fmtM(item.depth_tvd_m)} TVD` : item.depth_md_m != null ? `${fmtM(item.depth_md_m)} MD` : null
  const page = item.page
  return <li className="nw-result">
    <header><strong>{item.title || item.event_id || item.report_id || item.well_id}</strong>
      <VerificationBadge state={item.verification} />{item.confidence != null && <span className="nw-badge">confidence {fmtPct(item.confidence)}</span>}</header>
    {item.excerpt && <blockquote>“{item.excerpt}”</blockquote>}
    {item.mitigation && <p className="small"><strong>Mitigation:</strong> {item.mitigation}</p>}
    <p className="nw-cite"><Icon name="book" size={14} />{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.report_id} · page {page ?? '—'}</a> : [item.report_id, page != null ? `page ${page}` : null].filter(Boolean).join(' · ')}{[item.well_id, depth, item.formation].filter(Boolean).map(x => ` · ${x}`).join('')}</p>
  </li>
}

// Optional AI summary: Qwen 3.5 runs on the viewer's own GPU (WebGPU + ONNX); the cited answer never depends on it.
function BrowserSummary({ question, items }) {
  const [s, setS] = useState({ state: 'idle', text: '' })
  const unsubscribe = useRef(null)
  useEffect(() => () => unsubscribe.current?.(), [])
  const evidence = items.slice(0, 8)
  if (!evidence.length) return null
  if (!browserLlmSupported()) return <p className="muted small">AI summary needs a WebGPU browser (recent Chrome or Edge on a desktop). The cited answer above is complete without it.</p>
  const start = () => {
    setS({ state: 'loading', text: '' })
    unsubscribe.current = askBrowserLlm(buildMessages(question, evidence), m => setS(cur =>
      m.type === 'progress' ? { ...cur, label: m.label, pct: m.total ? Math.round((100 * m.loaded) / m.total) : null }
        : m.type === 'ready' ? { ...cur, state: 'generating', label: m.label }
          : m.type === 'token' ? { ...cur, text: cur.text + m.text }
            : m.type === 'done' ? { ...cur, state: 'done' }
              : m.type === 'error' ? { ...cur, state: 'error', message: m.code === 'unsupported' ? 'WebGPU is not available on this device.' : 'This device could not run the model (usually not enough GPU memory).' }
                : cur))
  }
  return <div className="nw-ai-summary">
    {s.state === 'idle' && <><button type="button" className="ghost" onClick={start}>Generate AI summary in your browser</button>
      <p className="muted small">Runs {MODELS[0].label} on your device (falls back to {MODELS[1].label}). First use downloads about {MODELS[0].downloadGb} GB from Hugging Face, then it is cached. Your question never leaves the browser.</p></>}
    {s.state === 'loading' && <p role="status">Loading {s.label || 'model'}{s.pct != null ? ` · ${s.pct}%` : '…'}</p>}
    {s.state === 'generating' && !s.text && <p role="status">Writing summary with {s.label}…</p>}
    {s.text && <><h3 className="small">AI summary · {s.label} · generated in your browser</h3><p translate="no" style={{ whiteSpace: 'pre-wrap' }}>{s.text}</p>
      <ol className="small muted">{evidence.map(i => <li key={i.event_id || i.report_id || i.well_id}>{[i.event_id || i.report_id || i.well_id, i.report_id && i.page != null ? `${i.report_id} p.${i.page}` : null].filter(Boolean).join(' · ')}</li>)}</ol>
      <p className="muted small">Advisory only. Numbers refer to the evidence listed above; verify against the cited sources before acting.</p></>}
    {s.state === 'error' && <p className="api-error" role="alert">{s.message} The cited answer above is unaffected.</p>}
  </div>
}

export function KnowledgeSearchPage() {
  const { wellId } = useNwis()
  const [query, setQuery] = useState('')
  const [asked, setAsked] = useState('')
  const search = useRequest()
  const result = search.data ? adaptQuery(search.data) : null
  const groups = groupResults(result)
  const total = groups.well.length + groups.event.length + groups.report.length
  const run = text => {
    setAsked(text)
    search.run(paths.query, { method: 'POST', timeout: 120000, body: { query: text, well_id: wellId || undefined, mode: 'nwis_evidence', retrieval: 'hybrid', request_id: crypto.randomUUID() } })
  }
  return <>
    <PageHeader title="Knowledge search" description="Search historical drilling evidence in natural language. Results are grouped by well, event and report, and every result carries its source, page, depth and formation." actions={<AgentAvatar size={48} />} />
    <section className="panel nw-panel">
      <form onSubmit={event => { event.preventDefault(); if (query.trim()) run(query.trim()) }}>
        <label>Question or search<textarea rows={2} value={query} onChange={e => setQuery(e.target.value)} maxLength={1000} required placeholder="e.g. Show stuck-pipe incidents in Tipam between 2400-2700 m TVD" /></label>
        <p className="muted small">Searches cited events in the ranked offsets of the active well ({wellId || 'none'}).</p>
        <button className="primary" disabled={search.loading || !query.trim()}>Search evidence</button>
      </form>
      <div className="nw-examples"><span className="muted small">Try:</span>{EXAMPLES.map(x => <button key={x} type="button" className="ghost" onClick={() => { setQuery(x); run(x) }}>{x}</button>)}</div>
    </section>
    {search.loading ? <div className="state state-loading nw-agent-state" role="status" aria-live="polite"><AgentAvatar size={28} className="brand-pulse" />Searching cited evidence in the ranked offsets…</div>
      : <NwisState request={search} what="knowledge search" />}
    {result && !result.recognized && <div className="state state-error" role="alert"><strong>Unrecognised search response</strong><p>The backend answered, but not in the NWIS evidence format (no evidence list). Nothing is shown rather than guessing.</p></div>}
    {result?.recognized && <>
      <p className="nw-result-summary">{total} results{result.mode ? ` · ${result.mode}` : ''} <SyntheticDataBadge data={result} /></p>
      {result.status === 'refused' && <div className="state state-empty" role="status"><strong>Refused</strong><p>{result.answer || 'NWIS does not answer this request.'}</p></div>}
      {result.summary && result.status !== 'refused' && <section className="panel nw-panel"><h2 className="nw-agent-heading"><AgentAvatar size={26} />Cited answer</h2><p>{result.summary}</p>{!result.citations.length && <p className="api-error">No citations were returned with this summary; treat it as unsupported.</p>}
        {result.citations.length > 0 && <BrowserSummary key={search.data?.execution_id || asked} question={asked} items={[...groups.event, ...groups.report, ...groups.well]} />}</section>}
      {!total && <div className="state state-empty"><strong>No matching evidence</strong><p>NWIS returned no cited records. It will not answer without evidence.</p></div>}
      <div className="nw-result-groups">{[['well', 'Wells'], ['event', 'Events'], ['report', 'Reports']].map(([key, label]) => groups[key].length > 0 && <section key={key} className="panel nw-panel" aria-labelledby={`rg-${key}`}>
        <h2 id={`rg-${key}`}>{label} <span className="muted small">{groups[key].length}</span></h2><ul className="nw-results">{groups[key].map((item, i) => <ResultItem key={`${key}-${i}`} item={item} />)}</ul></section>)}</div>
    </>}
  </>
}
