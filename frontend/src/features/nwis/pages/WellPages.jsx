import { Fragment, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import { Icon, PageHeader } from '../../../components/ui.jsx'
import { useResource } from '../../../hooks/useApi.js'
import { PRIMARY_HAZARDS, SCORE_COMPONENTS, closestExplanation, fmtKm, fmtM, fmtPct, fmtScore, humanize, listOf, paths, telemetrySeries } from '../nwisModel.js'
import { useNwis } from '../NwisContext.jsx'
import { useEventsFor, useNearby, useRisk } from '../hooks.js'
import CorrelationTracks from '../CorrelationTracks.jsx'
import { DataQualityBadge, DrillingEventChip, EventDots, EvidenceDrawer, LookaheadControl, NwisState, OffsetScoreBreakdown, RiskCard, ScoreBar, Sparkline, SyntheticDataBadge, VerificationBadge, WellContextBar } from '../components.jsx'
import { Panel } from './OverviewPages.jsx'

const isDrilling = w => w?.role === 'active' || w?.status === 'drilling'

export function WellsPage() {
  const { wellId, set } = useNwis()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const wells = useResource(paths.wells({ q: q.trim() || undefined, status: status || undefined }))
  const list = listOf(wells.data)
  return <>
    <PageHeader title="Well catalogue" description="Wells known to NWIS with location, trajectory class and record quality. Filtering happens on the server." />
    <form className="nw-filters" role="search" onSubmit={event => event.preventDefault()}>
      <label>Search wells<input value={q} onChange={e => setQ(e.target.value)} placeholder="Well name or ID" maxLength={80} /></label>
      <label>Status<select value={status} onChange={e => setStatus(e.target.value)}><option value="">Any</option>{['drilling', 'completed', 'suspended', 'abandoned'].map(s => <option key={s} value={s}>{humanize(s)}</option>)}</select></label>
    </form>
    <Panel title={`${wells.data?.total ?? list.length} wells`} data={wells.data}>
      <NwisState request={wells} what="the well catalogue" empty={wells.data && !list.length ? 'No wells match' : undefined} />
      {list.length > 0 && <div className="table-scroll" tabIndex={0} role="region" aria-label="Well catalogue"><table>
        <thead><tr><th>Well</th><th>Field</th><th>Status</th><th>Type</th><th>Trajectory</th><th>Spud</th><th>TD (MD)</th><th>Data quality</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
        <tbody>{list.map(w => <tr key={w.id} data-active={w.id === wellId || undefined}>
          <td><Link to={`/app/wells/${encodeURIComponent(w.id)}`}><strong>{w.name}</strong></Link>{w.id === wellId && <span className="nw-badge nw-context-badge">Active context</span>}</td>
          <td>{w.field || '—'}</td><td><span className="nw-status" data-status={w.status}>{humanize(w.status)}</span></td><td>{humanize(w.well_type)}</td><td>{w.trajectory_type || '—'}</td>
          <td>{w.spud_date?.slice(0, 4) || '—'}</td><td className="num">{fmtM(w.td_md_m)}</td><td><DataQualityBadge value={w.data_quality} /></td>
          <td>{isDrilling(w) && w.id !== wellId ? <button type="button" className="ghost" onClick={() => { set({ wellId: w.id }); navigate('/app/dashboard') }}>Set active</button> : null}</td></tr>)}</tbody></table></div>}
    </Panel>
  </>
}

function TelemetryStrip({ wellId }) {
  const telemetry = useResource(paths.telemetry(wellId, { window_s: 1800 }))
  const series = telemetrySeries(telemetry.data)
  if (!telemetry.data) return <NwisState request={telemetry} what="telemetry" />
  return <>
    <p className="nw-live-flag"><span className="nw-badge nw-replay">{telemetry.data.mode === 'live' ? 'LIVE' : 'SIMULATED / REPLAY DATA'}</span><span className="muted small">Latest value per channel the backend provides · <Link to="/app/live">Live drilling</Link></span></p>
    {series.length ? <ul className="nw-tele-strip">{series.map(s => { const last = s.points.at(-1)
      return <li key={s.id}><span className="nw-tele-name">{s.label}</span><strong>{last.v}<small> {s.unit}</small></strong>
        <Sparkline values={s.points.slice(-30).map(p => p.v)} label={`${s.label} last ${Math.min(30, s.points.length)} samples`} width={96} height={26} /></li> })}</ul>
      : <p className="muted">No channels with values were returned.</p>}
  </>
}

function OffsetWellView({ well }) {
  const { compare, toggle } = useNwis()
  const history = useEventsFor([well.id])
  return <>
    <div className="nw-dash-grid">
      <Panel title="Stratigraphy" data={well}>
        {(well.formations || []).length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Formations"><table><thead><tr><th>Formation</th><th>Top TVD</th><th>Base TVD</th><th>Confidence</th></tr></thead>
          <tbody>{well.formations.map(f => <tr key={f.name}><td>{f.name}{f.interpreted ? ' (interpreted)' : ''}</td><td className="num">{fmtM(f.top)}</td><td className="num">{fmtM(f.base)}</td><td className="num">{f.confidence == null ? 'unknown' : fmtPct(f.confidence)}</td></tr>)}</tbody></table></div>
          : <p className="muted">No formation intervals recorded.</p>}
      </Panel>
      <Panel title="Offset actions">
        <p className="muted">This is a historical offset well. Risk look-ahead and telemetry apply only to wells that are drilling.</p>
        <div className="toolbar"><button type="button" aria-pressed={compare.includes(well.id)} onClick={() => toggle('compare', well.id, 4)}>{compare.includes(well.id) ? 'In comparison' : 'Add to comparison'}</button>
          <Link className="button ghost" to="/app/correlation">Open correlation</Link><Link className="button ghost" to={`/app/events?well=${encodeURIComponent(well.id)}`}>All events</Link></div>
        {well.note && <p className="nw-note">{well.note}</p>}
      </Panel>
    </div>
    <Panel title="Recorded drilling events" data={history.request.data}>
      <NwisState request={history.request} what="events" empty={history.request.data && !history.events.length ? 'No events recorded for this well' : undefined} />
      <ul className="nw-event-list">{history.events.map(e => <li key={e.id}><DrillingEventChip type={e.type} severity={e.severity} /><span>{fmtM(e.depth_tvd_m)} TVD · {e.formation || '—'}</span><span className="muted small">{e.source?.report_id} p.{e.source?.page}</span><VerificationBadge state={e.verification} /></li>)}</ul>
    </Panel>
  </>
}

function ActiveCockpit({ well }) {
  const { lookahead } = useNwis()
  const risk = useRisk(well.id)
  const nearby = useNearby({ wellId: well.id })
  const [why, setWhy] = useState(null)
  const hazards = PRIMARY_HAZARDS.map(t => risk.hazards.find(h => h.type === t)).filter(Boolean).concat(risk.hazards.filter(h => !PRIMARY_HAZARDS.includes(h.type)))
  const evidenceTotal = hazards.reduce((n, h) => n + h.evidenceCount, 0)
  return <>
    <Panel title="Telemetry" data={well}><TelemetryStrip wellId={well.id} /></Panel>
    <Panel title={`Current hazards · next ${lookahead} m`} data={risk.request.data} action={<LookaheadControl />}>
      <NwisState request={risk.request} what="the risk look-ahead" />
      {hazards.length > 0 && <>
        <p className="muted small">{evidenceTotal} evidence records across {hazards.length} hazards · model {risk.request.data?.model_version || 'not reported'}</p>
        <div className="nw-risk-grid">{hazards.map(h => <RiskCard key={h.type} hazard={h} lookahead={lookahead} onWhy={setWhy} compact />)}</div></>}
    </Panel>
    <div className="nw-dash-grid">
      <Panel title="Upcoming formations" data={well}>
        {(well.upcoming_formations || []).length ? <ul className="nw-upcoming">{well.upcoming_formations.map(f => <li key={f.name}><strong>{f.name}</strong><span>top {fmtM(f.top_tvd_m)} TVD</span><span className="nw-badge">in {fmtM(f.distance_m)}</span>{f.confidence != null && <span className="muted small">confidence {fmtPct(f.confidence)}</span>}</li>)}</ul>
          : <p className="muted">No planned stratigraphic model supplied.</p>}
      </Panel>
      <Panel title="Top offset wells" data={nearby.request.data} action={<Link className="button ghost" to="/app/offset-analysis">Offset analysis</Link>}>
        <NwisState request={nearby.request} what="offsets" />
        <ol className="nw-why-offsets">{nearby.offsets.slice(0, 3).map(o => { const strong = SCORE_COMPONENTS.filter(([k]) => o.components[k] != null).sort(([a], [b]) => o.components[b] - o.components[a]).slice(0, 2)
          return <li key={o.id}><Link to={`/app/wells/${encodeURIComponent(o.id)}`}><strong>{o.id}</strong></Link> <span>score {fmtScore(o.total)} · {fmtKm(o.distanceKm)}</span>
            <p className="muted small">Strongest: {strong.map(([k, label]) => `${label.toLowerCase()} ${fmtScore(o.components[k])}`).join(', ')}</p></li> })}</ol>
      </Panel>
    </div>
    <EvidenceDrawer hazard={why} risk={risk.request.data} offsets={nearby.offsets} onClose={() => setWhy(null)} />
  </>
}

export function WellCockpitPage() {
  const { id } = useParams()
  const { wellId, set } = useNwis()
  const well = useResource(paths.well(id))
  const w = well.data
  return <>
    <PageHeader title={w?.name || id} description={w ? `${w.field || 'Field not recorded'} · ${humanize(w.status)} · ${humanize(w.well_type)} · ${w.trajectory_type || 'trajectory unknown'}` : 'Well record'}
      actions={w && isDrilling(w) && w.id !== wellId ? <button type="button" onClick={() => set({ wellId: w.id })}>Make active context</button> : null} />
    <NwisState request={well} what={`well ${id}`} />
    {w && <>
      <section className="panel nw-panel" aria-labelledby="well-id-h"><div className="section-heading"><h2 id="well-id-h">Identity and position</h2><span className="nw-panel-meta"><SyntheticDataBadge data={w} /><DataQualityBadge value={w.data_quality} /></span></div>
        <dl className="nw-kpis">
          {isDrilling(w) ? <>
            <div className="nw-kpi"><dt>MD</dt><dd>{fmtM(w.current_md_m)}</dd></div>
            <div className="nw-kpi"><dt>TVD / TVDSS</dt><dd>{fmtM(w.current_tvd_m)}</dd><p className="muted small">TVDSS {fmtM(w.current_tvdss_m)}</p></div>
            <div className="nw-kpi"><dt>Formation</dt><dd>{w.current_formation || '—'}</dd></div>
            <div className="nw-kpi"><dt>Hole section</dt><dd>{w.hole_section || '—'}</dd></div>
          </> : <>
            <div className="nw-kpi"><dt>TD</dt><dd>{fmtM(w.td_md_m)} MD</dd><p className="muted small">{fmtM(w.td_tvd_m)} TVD</p></div>
            <div className="nw-kpi"><dt>Spud</dt><dd>{w.spud_date || '—'}</dd></div>
          </>}
          <div className="nw-kpi"><dt>Surface location</dt><dd className="nw-mono">{Number.isFinite(w.lat) ? `${w.lat.toFixed(4)}°, ${w.lon.toFixed(4)}°` : '—'}</dd><p className="muted small">{w.trajectory_summary || w.trajectory_type}</p></div>
        </dl></section>
      {isDrilling(w) ? <ActiveCockpit well={w} /> : <OffsetWellView well={w} />}
    </>}
  </>
}

// "Active Well" navigation entry: the cockpit of whichever well is the active context.
export function ActiveWellRedirect() {
  const { wellId, wells } = useNwis()
  if (wellId) return <Navigate to={`/app/wells/${encodeURIComponent(wellId)}`} replace />
  return <><PageHeader title="Active well" /><NwisState request={wells} what="the well catalogue" empty={wells.data ? 'No drilling well in the catalogue. Choose a well in the Well Catalogue.' : undefined} /></>
}

export function OffsetAnalysisPage() {
  const { pinned, excluded, compare, toggle } = useNwis()
  const navigate = useNavigate()
  const nearby = useNearby()
  const [open, setOpen] = useState(null)
  const weights = nearby.request.data?.weights
  const explain = closestExplanation(nearby.offsets)
  // Pins/exclusions are a session view preference only; the backend ranking is shown unchanged in the Rank column.
  const rows = [...nearby.offsets].sort((a, b) => (excluded.includes(a.id) - excluded.includes(b.id)) || (pinned.includes(b.id) - pinned.includes(a.id)) || a.rank - b.rank)
  return <>
    <PageHeader title="Offset analysis" description="Which nearby wells are actually analogous? Every component score is shown so the ranking can be challenged. Ranking is deterministic, never produced by an LLM." />
    <WellContextBar radius />
    {explain && <aside className="nw-callout" aria-label="Closest well explanation"><Icon name="alert" /><p>
      <strong>{explain.closest.id}</strong> is the closest well ({fmtKm(explain.closest.distanceKm)}) but ranks <strong>#{explain.closest.rank}</strong>: its {explain.weakest.map(w => `${w.label.toLowerCase()} score is ${fmtScore(w.value)}`).join(' and ')}.
      <strong> {explain.top.id}</strong> ranks #1 at {fmtKm(explain.top.distanceKm)} with formation {fmtScore(explain.top.components.formation)} and depth overlap {fmtScore(explain.top.components.depth)}.
      {explain.closest.note && <> <em>{explain.closest.note}</em></>}</p></aside>}
    <Panel title="Ranked offsets" data={nearby.request.data} action={compare.length > 0 && <button type="button" className="primary" onClick={() => navigate('/app/correlation')}>Correlate {compare.length} selected</button>}>
      {weights && <p className="nw-formula"><span>Score = {SCORE_COMPONENTS.map(([k, label]) => weights[k] != null ? `${weights[k]}·${label.toLowerCase()}` : null).filter(Boolean).join(' + ')}</span>{nearby.request.data?.formula && <span className="muted small"> ({nearby.request.data.formula})</span>}</p>}
      <NwisState request={nearby.request} what="offset ranking" empty={nearby.request.data && !nearby.offsets.length ? 'No offsets in this radius' : undefined} />
      {rows.length > 0 && <div className="table-scroll" tabIndex={0} role="region" aria-label="Offset ranking with component scores"><table className="nw-offset-table">
        <thead><tr><th>Rank</th><th>Well</th><th>Distance</th><th>Total</th>{SCORE_COMPONENTS.map(([k, label]) => <th key={k}>{label}</th>)}<th>Events</th><th>Actions</th></tr></thead>
        <tbody>{rows.map(o => { const out = excluded.includes(o.id); const pin = pinned.includes(o.id)
          return <Fragment key={o.id}><tr data-excluded={out || undefined} data-pinned={pin || undefined}>
            <td className="num">{o.rank}</td>
            <td className="nw-nowrap"><button type="button" className="nw-linkish" aria-expanded={open === o.id} onClick={() => setOpen(open === o.id ? null : o.id)}>{o.id}</button>{pin && <span className="nw-badge">Pinned</span>}{out && <span className="nw-badge">Excluded</span>}</td>
            <td className="num">{fmtKm(o.distanceKm)}</td><td className="num"><strong>{fmtScore(o.total)}</strong></td>
            {SCORE_COMPONENTS.map(([k, label]) => <td key={k}><ScoreBar value={o.components[k]} label={label} /></td>)}
            <td><EventDots counts={o.eventCounts} /></td>
            <td><span className="nw-row-actions">
              <button type="button" className="ghost" aria-pressed={pin} onClick={() => toggle('pinned', o.id)}>{pin ? 'Unpin' : 'Pin'}</button>
              <button type="button" className="ghost" aria-pressed={compare.includes(o.id)} disabled={out} onClick={() => toggle('compare', o.id, 4)}>Compare</button>
              <button type="button" className="ghost" aria-pressed={out} onClick={() => toggle('excluded', o.id)}>{out ? 'Include' : 'Exclude'}</button></span></td></tr>
            {open === o.id && <tr className="nw-expand"><td colSpan={SCORE_COMPONENTS.length + 6}><div className="nw-expand-body">
              <OffsetScoreBreakdown offset={o} weights={weights} />
              <div><p>{o.well.trajectory_type} · {humanize(o.well.well_type)} · TD {fmtM(o.well.td_md_m)} MD · <DataQualityBadge value={o.well.data_quality} /></p>
                {o.formationAtDepth && <p>At the active well's current TVD this well is in <strong>{o.formationAtDepth}</strong>.</p>}
                {o.note && <p className="nw-note">{o.note}</p>}<Link to={`/app/wells/${encodeURIComponent(o.id)}`}>Open well record</Link></div></div></td></tr>}
          </Fragment> })}</tbody></table></div>}
      <p className="muted small">Pin, compare and exclude are session view preferences. They do not change the backend ranking or the risk engine until the backend accepts analyst overrides.</p>
    </Panel>
  </>
}

export function CorrelationPage() {
  const { wellId, lookahead, compare, toggle } = useNwis()
  const nearby = useNearby({ radiusKm: 20 })
  const correlation = useResource(wellId ? paths.correlation(wellId, { offsets: compare, lookahead_m: lookahead, depth_ref: 'tvd' }) : null)
  const shown = (correlation.data?.tracks || []).filter(t => t.role !== 'active').map(t => t.well_id)
  return <>
    <PageHeader title="Formation correlation" description="Active well and selected offsets on one TVD axis, with formation intervals, drilling events, casing points and the look-ahead window. Interpreted intervals are hatched; unknown tops are marked." />
    <WellContextBar lookahead />
    <section className="panel nw-panel" aria-labelledby="corr-pick"><div className="section-heading"><h2 id="corr-pick">Offsets in the comparison</h2>
      <span className="muted small">{compare.length ? `${compare.length} of 4 selected` : 'None selected: the backend shows its top-ranked offsets'}</span></div>
      <div className="nw-pick">{nearby.offsets.slice(0, 10).map(o => <button key={o.id} type="button" className="nw-pick-chip" aria-pressed={compare.includes(o.id)} disabled={!compare.includes(o.id) && compare.length >= 4}
        onClick={() => toggle('compare', o.id, 4)}>{o.id}<small>{fmtScore(o.total)}</small></button>)}
        {nearby.request.error && <span className="muted small">Offset list unavailable.</span>}</div>
    </section>
    <Panel title={`Correlation · ${[correlation.data?.tracks?.[0]?.name || wellId, ...shown].filter(Boolean).join(' · ')}`} data={correlation.data}>
      <NwisState request={correlation} what="the correlation" />
      {correlation.data && <CorrelationTracks data={correlation.data} />}
    </Panel>
  </>
}
