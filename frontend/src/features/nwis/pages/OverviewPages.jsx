import { Suspense, lazy, useState } from 'react'
import { Link } from 'react-router'
import { PageHeader } from '../../../components/ui.jsx'
import { HAZARDS, PRIMARY_HAZARDS, eventMatrix, fmtAge, fmtKm, fmtM, fmtPct, fmtScore, freshness, hazardLabel, humanize, listOf, paths } from '../nwisModel.js'
import { useNwis } from '../NwisContext.jsx'
import { useEventsFor, useNearby, useNow, useNwisResource, useRisk } from '../hooks.js'
import { adaptAdvisoryList, adaptTelemetry } from '../adapters.js'
import { DataQualityBadge, DrillingEventChip, NwisState, OffsetScoreBreakdown, RiskCard, SyntheticDataBadge, WellContextBar } from '../components.jsx'

const NearbyMap = lazy(() => import('../NearbyMap.jsx'))
const MapFallback = () => <p className="nw-map-note" role="status">Loading map…</p>

export function Panel({ title, children, action, data, className = '', id }) {
  return <section className={`panel nw-panel ${className}`} aria-labelledby={id}><div className="section-heading"><h2 id={id}>{title}</h2><span className="nw-panel-meta"><SyntheticDataBadge data={data} />{action}</span></div>{children}</section>
}

function Kpi({ label, value, hint }) {
  return <div className="nw-kpi"><dt>{label}</dt><dd>{value}</dd>{hint && <p className="muted small">{hint}</p>}</div>
}

export function DashboardPage() {
  const { well, wellId, lookahead, radiusKm, wells } = useNwis()
  const risk = useRisk()
  const nearby = useNearby()
  const advisories = useNwisResource(wellId ? paths.advisories({ well_id: wellId }) : null, adaptAdvisoryList)
  const telemetry = useNwisResource(wellId ? paths.telemetry(wellId, { window_s: 600 }) : null, adaptTelemetry)
  const offsetIds = nearby.offsets.map(o => o.id)
  const history = useEventsFor(offsetIds.length ? offsetIds : null, { limit: 500 })
  const usable = nearby.offsets.filter(o => (o.total ?? 0) >= 0.55)
  const now = useNow()
  const fresh = freshness(telemetry.data?.as_of, now, telemetry.data?.stale_after_s)
  const matrix = eventMatrix(history.events)
  const verified = history.events.filter(e => e.verification === 'verified').length
  const unassigned = history.events.filter(e => !e.formation).length
  const hazards = PRIMARY_HAZARDS.map(type => risk.hazards.find(h => h.type === type)).filter(Boolean)

  return <>
    <PageHeader title="Drilling overview" description="Active-well context, hazard look-ahead and nearby offset coverage. Every value is read from the NWIS API; nothing is estimated in the browser." />
    <WellContextBar radius lookahead />
    {!wellId && <NwisState request={wells} what="the well catalogue" empty={wells.data ? 'No active well in the catalogue' : undefined} />}
    {wellId && <>
      <section className="panel nw-panel" aria-labelledby="active-well-h">
        <div className="section-heading"><h2 id="active-well-h">Active well · {well?.name || wellId}</h2><span className="nw-panel-meta"><SyntheticDataBadge data={well} /><Link className="button ghost" to={`/app/wells/${encodeURIComponent(wellId)}`}>Open cockpit</Link></span></div>
        <dl className="nw-kpis">
          <Kpi label="Current MD" value={fmtM(well?.current_md_m)} />
          <Kpi label="Current TVD" value={fmtM(well?.current_tvd_m)} hint={well?.current_tvdss_m != null ? `TVDSS ${fmtM(well.current_tvdss_m)}` : null} />
          <Kpi label="Current formation" value={well?.current_formation || '—'} hint={well?.hole_section} />
          <Kpi label="Look-ahead window" value={well?.current_md_m != null ? `${fmtM(well.current_md_m)} → ${fmtM(well.current_md_m + lookahead)}` : `next ${lookahead} m`} hint="MD, selectable 50 / 100 / 150 m" />
        </dl>
      </section>

      <Panel title={`Hazard look-ahead · next ${lookahead} m`} data={risk.request.data} action={<Link className="button ghost" to="/app/risk">Risk look-ahead</Link>}>
        <NwisState request={risk.request} what="the risk look-ahead" empty={risk.request.data && !hazards.length ? 'No hazard assessments returned for this interval' : undefined} />
        {hazards.length > 0 && <div className="nw-risk-grid is-compact">{hazards.map(h => <RiskCard key={h.type} hazard={h} lookahead={lookahead} compact />)}</div>}
      </Panel>

      <div className="nw-dash-grid">
        <Panel title={`Offset coverage · ${radiusKm} km`} data={nearby.request.data} action={<Link className="button ghost" to="/app/offset-analysis">Offset analysis</Link>}>
          <NwisState request={nearby.request} what="nearby offsets" empty={nearby.request.data && !nearby.offsets.length ? `No offset wells within ${radiusKm} km` : undefined} />
          {nearby.offsets.length > 0 && <>
            <p className="nw-big">{usable.length}<span> usable analogs of {nearby.offsets.length} wells in radius</span></p>
            <p className="muted small">Usable = backend total score ≥ 0.55. Ranking is by formation, depth, trajectory, context and data quality, not distance alone.</p>
            <ol className="nw-top-offsets">{nearby.offsets.slice(0, 3).map(o => <li key={o.id}><Link to={`/app/wells/${encodeURIComponent(o.id)}`}>{o.id}</Link><span>score {fmtScore(o.total)}</span><span>{fmtKm(o.distanceKm)}</span></li>)}</ol>
          </>}
        </Panel>
        <Panel title="Map mini-view" data={nearby.request.data} action={<Link className="button ghost" to="/app/map">Open map</Link>}>
          {well && nearby.request.data ? <Suspense fallback={<MapFallback />}><NearbyMap compact center={{ id: well.id, label: well.name, lat: well.lat, lon: well.lon }} offsets={nearby.offsets} radiusKm={radiusKm} label="Nearby wells mini-map" /></Suspense>
            : <NwisState request={nearby.request} what="the map" />}
        </Panel>
        <Panel title="Recent alerts" data={advisories.data} action={<Link className="button ghost" to="/app/advisories">Advisories</Link>}>
          <NwisState request={advisories} what="advisories" empty={advisories.data && !listOf(advisories.data).length ? 'No alerts for this well' : undefined} />
          <ul className="nw-alert-list">{listOf(advisories.data).slice(0, 4).map(a => <li key={a.id}>
            <Link to={`/app/advisories?id=${encodeURIComponent(a.id)}`}><DrillingEventChip type={a.hazard} /></Link>
            <span className="nw-status" data-status={a.status}>{humanize(a.status)}</span><span className="muted small">{fmtPct(a.probability)} · {a.created_at ? new Date(a.created_at).toLocaleTimeString() : ''}</span></li>)}</ul>
        </Panel>
        <Panel title="Data quality" data={well}>
          <dl className="nw-quality">
            <div><dt>Active-well record</dt><dd><DataQualityBadge value={well?.data_quality} /></dd></div>
            <div><dt>Telemetry freshness</dt><dd>{telemetry.error ? <span className="nw-status" data-status="stale">Unavailable</span> : telemetry.data ? <span className="nw-status" data-status={fresh.state}>{humanize(fresh.state)} · {fmtAge(fresh.ageS)}</span> : '—'}{telemetry.data?.mode && <span className="nw-badge nw-replay">{String(telemetry.data.mode).toUpperCase()}</span>}</dd></div>
            <div><dt>Offset events verified</dt><dd>{history.events.length ? `${verified} of ${history.events.length} (${fmtPct(verified / history.events.length)})` : '—'}</dd></div>
            <div><dt>Missing formation mappings</dt><dd>{history.events.length ? unassigned : '—'}</dd></div>
          </dl>
        </Panel>
      </div>

      <Panel title="Historical events by formation and hazard" data={history.request.data} action={<Link className="button ghost" to="/app/events">Drilling events</Link>}>
        <p className="muted small">Events recorded in the offset wells currently within {radiusKm} km.</p>
        <NwisState request={history.request} what="historical events" empty={history.request.data && !history.events.length ? 'No historical events recorded for these offsets' : undefined} />
        {history.events.length > 0 && <div className="table-scroll" tabIndex={0} role="region" aria-label="Event distribution"><table className="nw-matrix">
          <thead><tr><th scope="col">Formation</th>{matrix.types.map(t => <th key={t} scope="col">{hazardLabel(t)}</th>)}<th scope="col">Total</th></tr></thead>
          <tbody>{matrix.formations.map(f => { const row = matrix.counts[f]; const total = Object.values(row).reduce((a, b) => a + b, 0)
            return <tr key={f} data-active={f === well?.current_formation || undefined}><th scope="row">{f}{f === well?.current_formation ? ' (current)' : ''}</th>
              {matrix.types.map(t => <td key={t} className="num" data-heat={Math.min(4, row[t])}>{row[t] || ''}</td>)}<td className="num"><strong>{total}</strong></td></tr> })}</tbody>
        </table></div>}
      </Panel>
    </>}
  </>
}

const FILTERS = {
  hazard: Object.keys(HAZARDS),
  well_type: ['development', 'exploratory'],
  trajectory_type: ['vertical', 'deviated', 'J-shape', 'S-shape', 'horizontal'],
}

export function MapPage() {
  const { well, radiusKm, toggle, compare } = useNwis()
  const [filters, setFilters] = useState({})
  const [selected, setSelected] = useState(null)
  const nearby = useNearby({ filters })
  const choice = nearby.offsets.find(o => o.id === selected) || null
  const formations = (well?.formations || []).map(f => f.name)
  const update = (key, value) => setFilters(current => ({ ...current, [key]: value || undefined }))
  return <>
    <PageHeader title="Nearby wells map" description="The backend runs the radius query and scores each offset; the map draws its result. Select a well to open its offset context." />
    <WellContextBar radius />
    <form className="nw-filters" onSubmit={event => event.preventDefault()} aria-label="Offset filters">
      <label>Formation<select value={filters.formation || ''} onChange={e => update('formation', e.target.value)}><option value="">Any</option>{formations.map(f => <option key={f}>{f}</option>)}</select></label>
      <label>Hazard history<select value={filters.hazard || ''} onChange={e => update('hazard', e.target.value)}><option value="">Any</option>{FILTERS.hazard.map(h => <option key={h} value={h}>{hazardLabel(h)}</option>)}</select></label>
      <label>Well type<select value={filters.well_type || ''} onChange={e => update('well_type', e.target.value)}><option value="">Any</option>{FILTERS.well_type.map(v => <option key={v} value={v}>{humanize(v)}</option>)}</select></label>
      <label>Trajectory<select value={filters.trajectory_type || ''} onChange={e => update('trajectory_type', e.target.value)}><option value="">Any</option>{FILTERS.trajectory_type.map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Min data quality<select value={filters.min_quality || ''} onChange={e => update('min_quality', e.target.value)}><option value="">Any</option><option value="0.5">≥ 0.50</option><option value="0.75">≥ 0.75</option></select></label>
    </form>
    <div className="nw-map-layout">
      <section className="panel nw-panel nw-map-panel" aria-label="Map">
        {well ? <Suspense fallback={<MapFallback />}><NearbyMap center={{ id: well.id, label: well.name, lat: well.lat, lon: well.lon }} offsets={nearby.offsets} radiusKm={radiusKm} selectedId={selected} onSelect={setSelected} /></Suspense>
          : <NwisState request={nearby.request} what="the active well" />}
      </section>
      <aside className="panel nw-panel nw-offset-detail" aria-live="polite" aria-label="Selected offset">
        {choice ? <>
          <div className="section-heading"><h2>{choice.id}</h2><span className="nw-rank">#{choice.rank}</span></div>
          <p className="muted small">{fmtKm(choice.distanceKm)} from {well?.name} · total score <strong>{fmtScore(choice.total)}</strong> · {choice.well.trajectory_type} · TD {fmtM(choice.well.td_md_m)} MD</p>
          <p><DataQualityBadge value={choice.well.data_quality} /> {choice.formationAtDepth && <span className="nw-badge">At active TVD: {choice.formationAtDepth}</span>}</p>
          {choice.note && <p className="nw-note">{choice.note}</p>}
          <OffsetScoreBreakdown offset={choice} weights={nearby.request.data?.weights} />
          <p className="nw-chips">{Object.entries(choice.eventCounts).map(([type, count]) => <DrillingEventChip key={type} type={type}> ×{count}</DrillingEventChip>)}{!Object.keys(choice.eventCounts).length && <span className="muted small">No historical events recorded.</span>}</p>
          <div className="toolbar"><Link className="button" to={`/app/wells/${encodeURIComponent(choice.id)}`}>Open well</Link>
            <button type="button" aria-pressed={compare.includes(choice.id)} onClick={() => toggle('compare', choice.id, 4)}>{compare.includes(choice.id) ? 'In comparison' : 'Add to comparison'}</button>
            <Link className="button ghost" to="/app/correlation">Correlation</Link></div>
        </> : <><h2>Offset context</h2><p className="muted">Select a well on the map or in the table to see why it ranks where it does.</p></>}
      </aside>
    </div>
    <section className="panel nw-panel"><div className="section-heading"><h2>Offsets returned for {radiusKm} km</h2><span className="nw-panel-meta"><SyntheticDataBadge data={nearby.request.data} /></span></div>
      <NwisState request={nearby.request} what="nearby offsets" empty={nearby.request.data && !nearby.offsets.length ? 'No offset wells match this radius and these filters' : undefined} />
      {nearby.offsets.length > 0 && <div className="table-scroll" tabIndex={0} role="region" aria-label="Nearby offset wells"><table>
        <thead><tr><th>Rank</th><th>Well</th><th>Distance</th><th>Total score</th><th>Trajectory</th><th>Events</th><th>Data quality</th><th><span className="visually-hidden">Select</span></th></tr></thead>
        <tbody>{nearby.offsets.map(o => <tr key={o.id} aria-selected={o.id === selected}><td className="num">{o.rank}</td><td>{o.id}</td><td className="num">{fmtKm(o.distanceKm)}</td><td className="num">{fmtScore(o.total)}</td>
          <td>{o.well.trajectory_type || '—'}</td><td className="num">{Object.values(o.eventCounts).reduce((a, b) => a + b, 0)}</td><td><DataQualityBadge value={o.well.data_quality} /></td>
          <td><button type="button" className="ghost" aria-pressed={o.id === selected} onClick={() => setSelected(o.id)}>Select</button></td></tr>)}</tbody></table></div>}
    </section>
  </>
}
