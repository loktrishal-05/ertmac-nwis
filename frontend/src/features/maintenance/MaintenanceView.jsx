import { useMemo, useState } from 'react'
import { useResource } from '../../hooks/useApi.js'
import { BarList, TimeSeriesChart } from '../../components/charts.jsx'
import { EmptyState, ErrorState, Icon, LoadingState } from '../../components/ui.jsx'
import { SERIES_COLORS, dedupeWorkOrders, defaultSession, sumBy, recordingSessions, sensorSeries, seriesStats, workOrderBoard } from '../insights/insightsModel.js'

const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const stamp = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const round = v => +v.toFixed(2)

function useSensorSeries() {
  const request = useResource('/sensors/readings?limit=2000')
  const series = useMemo(() => sensorSeries(request.data?.results).map((s, i) => ({ ...s, label: `${s.equipment} ${s.measurement}`, color: SERIES_COLORS[i % SERIES_COLORS.length] })), [request.data])
  return { request, series }
}

export function RequestState({ request, children, empty, isEmpty }) {
  if (request.error) return <ErrorState title="Could not load live data" message={request.error.message} onRetry={request.refresh} />
  if (!request.data) return <LoadingState label="Loading live data…" />
  if (isEmpty) return <EmptyState title={empty} />
  return children
}

const clock = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })
const sessionLabel = session => `${dateOnly.format(session.start)}, ${clock.format(session.start)}–${clock.format(session.end)} · ${session.count} readings${session.future ? ' · future-dated' : ''}`

export function SensorTrends({ compact = false }) {
  const { request, series } = useSensorSeries()
  const sessions = useMemo(() => recordingSessions(series), [series])
  const [sessionId, setSessionId] = useState(null)
  const [hidden, setHidden] = useState([])
  const [threshold, setThreshold] = useState('')
  const session = sessions.find(s => s.id === sessionId) || defaultSession(sessions)
  const inSession = session?.series || []
  const shown = inSession.filter(s => !hidden.includes(s.id))
  const toggle = id => setHidden(value => value.includes(id) ? value.filter(v => v !== id) : [...value, id])
  const limit = threshold === '' ? null : Number(threshold)
  const above = Number.isFinite(limit) ? shown.flatMap(s => s.points).filter(p => p.v > limit).length : 0
  const total = shown.reduce((n, s) => n + s.points.length, 0)
  return <RequestState request={request} isEmpty={!series.length} empty="No sensor readings have been ingested yet.">
    <div className="trend-controls">
      <div className="series-legend" role="group" aria-label="Series">{inSession.map(s => { const stats = seriesStats(s.points)
        return <button key={s.id} type="button" className="series-chip" aria-pressed={!hidden.includes(s.id)} onClick={() => toggle(s.id)}>
          <i style={{ background: s.color }} aria-hidden="true" /><span className="series-chip-name"><strong className="identifier">{s.equipment}</strong> <span className="identifier muted">{s.id}</span></span>
          {!compact && <span className="series-chip-stats">peak <b>{round(stats.max)}</b> {s.unit} · last {round(stats.last)} {s.unit}</span>}</button> })}</div>
      {compact ? <p className="muted small session-caption">Recording session {session && sessionLabel(session)}</p>
        : <label className="session-select">Recording session<select value={session?.id || ''} onChange={event => { setSessionId(event.target.value); setHidden([]) }}>
          {sessions.map(s => <option key={s.id} value={s.id}>{sessionLabel(s)}</option>)}</select></label>}
      {!compact && <label className="threshold-input">Your threshold<span className="with-unit"><input type="number" inputMode="decimal" step="0.1" min="0" value={threshold} placeholder="e.g. 7.1"
        onChange={event => setThreshold(event.target.value)} aria-describedby="threshold-hint" /><span>{series[0]?.unit}</span></span></label>}
    </div>
    {!compact && <p id="threshold-hint" className="muted small threshold-hint">{Number.isFinite(limit) ? <><b>{above}</b> of {total} shown readings are above your threshold of {limit} {series[0]?.unit}. Thresholds are yours; the Workbench never invents one.</> : 'Enter a threshold to mark it on the chart. Thresholds are supplied by people; the Workbench never invents one.'}</p>}
    <TimeSeriesChart key={session?.id} series={shown} unit={series[0]?.unit || ''} height={compact ? 230 : 320} threshold={Number.isFinite(limit) ? limit : null}
      label={`${shown.map(s => s.label).join(' and ') || 'No series selected'} during the selected recording session`} emptyText="Select at least one series." />
    {!compact && session && <p className="muted small">Source {session.sources.length === 1 ? 'file' : 'files'}: {session.sources.join(', ') || 'not reported'}. Each reading links to its source row in the data table.</p>}
  </RequestState>
}

function WorkOrderCard({ order, selected, onSelect }) {
  return <button type="button" className="wo-card" data-type={order.maintenance_type} aria-pressed={selected} onClick={() => onSelect(order)}>
    <span className="wo-top"><span className="identifier wo-id">{order.work_order_id}</span><span className="wo-type">{order.maintenance_type}</span></span>
    <span className="wo-desc">{order.description}</span>
    <span className="wo-meta"><span className="identifier">{order.equipment_tag}</span><span>{dateOnly.format(Date.parse(order.maintenance_date))}</span>
      {order.downtime_hours != null && <span>{order.downtime_hours} h downtime</span>}
      {order.ingests > 1 && <span className="wo-ingests" title="The same record was ingested more than once">ingested ×{order.ingests}</span>}</span>
  </button>
}

function Inspector({ order, onClose }) {
  if (!order) return <aside className="wo-inspector is-empty" aria-label="Work order details"><Icon name="tool" size={22} /><p>Select a work order to read its record, technician notes and source citation.</p></aside>
  const rows = [['Equipment', <span className="identifier">{order.equipment_tag}</span>], ['Type', order.maintenance_type], ['Status', order.status], ['Date', dateOnly.format(Date.parse(order.maintenance_date))],
    ['Downtime', order.downtime_hours != null ? `${order.downtime_hours} h` : 'Not recorded'], ['Failure mode', order.failure_mode || 'Not recorded'], ['Parts replaced', order.parts_replaced || 'None recorded']]
  return <aside className="wo-inspector" aria-label={`Work order ${order.work_order_id}`}>
    <header><span className="identifier wo-id">{order.work_order_id}</span><button type="button" className="icon-button ghost" onClick={onClose} aria-label="Close details"><Icon name="close" size={18} /></button></header>
    <h3>{order.description}</h3>
    <dl className="kv">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
    {order.technician_notes && <p className="wo-notes">{order.technician_notes}</p>}
    <div className="wo-citations"><p className="muted small">{order.citations?.length > 1 ? `Ingested ${order.citations.length} times; every source row is kept:` : 'Source'}</p>
      <ul>{(order.citations?.length ? order.citations : [order.citation]).map((citation, index) => <li key={index} className="wo-citation"><Icon name="book" size={16} />
        <span>{citation?.source_filename || 'Source not reported'}{citation?.source_row_number ? ` · row ${citation.source_row_number}` : ''}
          {citation?.source_sha256 && <><br /><code title={citation.source_sha256}>sha256 {citation.source_sha256.slice(0, 12)}…</code></>}</span></li>)}</ul></div>
    <p className="muted small">Ingested {order.ingested_at ? stamp.format(Date.parse(order.ingested_at)) : 'at an unknown time'}.</p>
  </aside>
}

export function WorkOrderBoard() {
  const request = useResource('/maintenance/history?limit=2000')
  const orders = useMemo(() => dedupeWorkOrders(request.data?.results), [request.data])
  const [type, setType] = useState('all')
  const [selected, setSelected] = useState(null)
  const types = useMemo(() => ['all', ...new Set(orders.map(o => o.maintenance_type).filter(Boolean))], [orders])
  const board = useMemo(() => workOrderBoard(type === 'all' ? orders : orders.filter(o => o.maintenance_type === type)), [orders, type])
  return <RequestState request={request} isEmpty={!orders.length} empty="No maintenance records have been ingested yet.">
    <div className="board-toolbar">
      <div className="segmented" role="group" aria-label="Filter by maintenance type">{types.map(value =>
        <button key={value} type="button" aria-pressed={type === value} onClick={() => setType(value)}>{value === 'all' ? 'All types' : value}
          <span className="count">{value === 'all' ? orders.length : orders.filter(o => o.maintenance_type === value).length}</span></button>)}</div>
      <p className="muted small">Read-only: statuses come from the maintenance system of record. Nothing here changes plant state.</p>
    </div>
    <div className="board-layout">
      <div className="kanban">{board.map(column => <section key={column.id} className="kanban-col" data-status={column.id} aria-label={`${column.label}, ${column.items.length} work orders`}>
        <header><span className="col-dot" aria-hidden="true" /><h3>{column.label}</h3><span className="count">{column.items.length}</span></header>
        <div className="kanban-list">{column.items.length ? column.items.map(order =>
          <WorkOrderCard key={order.id} order={order} selected={selected?.id === order.id} onSelect={setSelected} />) : <p className="muted small kanban-empty">None</p>}</div>
      </section>)}</div>
      <Inspector order={selected} onClose={() => setSelected(null)} />
    </div>
  </RequestState>
}

export function WorkOrderSummary() {
  const request = useResource('/maintenance/history?limit=2000')
  const orders = dedupeWorkOrders(request.data?.results) // Repeat ingests must not inflate counts or downtime.
  const open = orders.filter(o => o.status === 'open').length
  return <RequestState request={request} isEmpty={!orders.length} empty="No maintenance records yet.">
    <div className="split-bar" role="img" aria-label={`${open} open and ${orders.length - open} closed work orders`}>
      <span className="split-open" style={{ flexGrow: open || 0.001 }} /><span className="split-closed" style={{ flexGrow: orders.length - open || 0.001 }} /></div>
    <p className="split-legend"><span><i className="dot-open" aria-hidden="true" /><b>{open}</b> open</span><span><i className="dot-closed" aria-hidden="true" /><b>{orders.length - open}</b> closed</span></p>
    <h3 className="dash-subhead">Downtime by type <small className="muted">distinct records</small></h3>
    <BarList data={sumBy(orders, 'maintenance_type', 'downtime_hours')} label="Downtime hours by maintenance type" unitLabel="h" />
  </RequestState>
}
