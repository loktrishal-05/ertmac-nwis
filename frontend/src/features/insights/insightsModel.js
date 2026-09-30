// Pure shaping of live backend records into chart and board data. Nothing here invents a value.

export const SERIES_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)']

// Physical measurements only; ingestion fixture markers (unit "flag") are not a trend.
export function sensorSeries(readings = []) {
  const groups = new Map()
  for (const reading of readings) {
    if (typeof reading?.value !== 'number' || reading.unit === 'flag') continue
    const time = Date.parse(reading.timestamp)
    if (!Number.isFinite(time)) continue
    const id = reading.sensor_tag
    if (!groups.has(id)) groups.set(id, { id, equipment: reading.equipment_tag, measurement: reading.measurement, unit: reading.unit, points: [] })
    groups.get(id).points.push({ t: time, v: reading.value, quality: reading.quality, source: reading.citation?.source_filename, row: reading.citation?.source_row_number })
  }
  return [...groups.values()]
    .map(series => ({ ...series, points: series.points.sort((a, b) => a.t - b.t) }))
    .sort((a, b) => b.points.length - a.points.length || a.id.localeCompare(b.id))
}

// Readings arrive in recording sessions (contiguous runs from one ingest). Charting sessions years apart on one
// line would invent ramps between them, so the chart shows one session at a time.
export function recordingSessions(series = [], gapMs = 6 * 3600000, now = Date.now()) {
  const all = series.flatMap(s => s.points.map(p => ({ ...p, seriesId: s.id }))).sort((a, b) => a.t - b.t)
  const sessions = []
  for (const point of all) {
    const current = sessions[sessions.length - 1]
    if (!current || point.t - current.end > gapMs) sessions.push({ start: point.t, end: point.t, points: [point] })
    else { current.end = point.t; current.points.push(point) }
  }
  return sessions.map((session, index) => ({
    id: `s${index}`,
    start: session.start,
    end: session.end,
    count: session.points.length,
    future: session.start > now,
    sources: [...new Set(session.points.map(p => p.source).filter(Boolean))],
    series: series.map(s => ({ ...s, points: s.points.filter(p => p.t >= session.start && p.t <= session.end) })).filter(s => s.points.length),
  })).reverse()
}

// Newest session that is not dated in the future; future-dated fixture runs stay selectable but never lead.
export const defaultSession = sessions => sessions.find(s => !s.future) || sessions[0] || null

export function seriesStats(points = []) {
  if (!points.length) return null
  const values = points.map(p => p.v)
  const last = points[points.length - 1]
  return { count: points.length, min: Math.min(...values), max: Math.max(...values), last: last.v, lastAt: last.t, first: points[0].v }
}

// Axis ticks that land on round numbers (1, 2, 2.5, 5 × 10^n).
export function niceTicks(min, max, count = 4) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (min === max) { min -= 1; max += 1 }
  const raw = (max - min) / count
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map(f => f * power).find(s => s >= raw)
  const start = Math.floor(min / step) * step
  const ticks = []
  // Always end at or above the maximum, so no value can plot past the top gridline.
  for (let v = start; ticks.length < 50; v += step) { ticks.push(+v.toFixed(10)); if (v >= max - 1e-9) break }
  return ticks
}

export const WORK_ORDER_COLUMNS = [
  { id: 'open', label: 'Open' },
  { id: 'in_progress', label: 'In progress' },
  { id: 'closed', label: 'Closed' },
]

// Columns follow the statuses the maintenance system of record reports; unknown statuses get their own column.
export function workOrderBoard(orders = []) {
  const columns = new Map(WORK_ORDER_COLUMNS.map(column => [column.id, { ...column, items: [] }]))
  for (const order of orders) {
    const status = (order?.status || 'unknown').toLowerCase()
    if (!columns.has(status)) columns.set(status, { id: status, label: status.replaceAll('_', ' '), items: [] })
    columns.get(status).items.push(order)
  }
  for (const column of columns.values()) column.items.sort((a, b) => Date.parse(b.maintenance_date) - Date.parse(a.maintenance_date))
  // "In progress" only appears when the source reports it; open and closed always frame the board.
  return [...columns.values()].filter(column => column.items.length || column.id === 'open' || column.id === 'closed')
}

// The same work order ingested more than once (same id, equipment and status) is one card that says so,
// keeping every source citation; distinct records are never merged.
export function dedupeWorkOrders(orders = []) {
  const groups = new Map()
  for (const order of orders) {
    const key = [order?.work_order_id, order?.equipment_tag, order?.status, order?.maintenance_date, order?.description].join('|')
    if (!groups.has(key)) groups.set(key, { ...order, ingests: 0, citations: [] })
    const group = groups.get(key)
    group.ingests += 1
    if (order?.citation) group.citations.push(order.citation)
  }
  return [...groups.values()]
}

export function countBy(items = [], key) {
  const counts = new Map()
  for (const item of items) {
    const value = typeof key === 'function' ? key(item) : item?.[key]
    if (value == null) continue
    counts.set(value, (counts.get(value) || 0) + 1)
  }
  return [...counts.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value || String(a.label).localeCompare(String(b.label)))
}

export function sumBy(items = [], key, field) {
  const sums = new Map()
  for (const item of items) {
    const label = item?.[key], value = Number(item?.[field])
    if (label == null || !Number.isFinite(value)) continue
    sums.set(label, (sums.get(label) || 0) + value)
  }
  return [...sums.entries()].map(([label, value]) => ({ label, value: +value.toFixed(2) })).sort((a, b) => b.value - a.value)
}

// Audit events per UTC day across the observed span (days with no events are real zeros).
export function eventsPerDay(events = []) {
  const days = events.map(e => Date.parse(e?.occurred_at)).filter(Number.isFinite).map(t => Math.floor(t / 86400000))
  if (!days.length) return []
  const first = Math.min(...days), last = Math.max(...days)
  const counts = new Map()
  for (const day of days) counts.set(day, (counts.get(day) || 0) + 1)
  const out = []
  for (let day = first; day <= last; day += 1) out.push({ day, t: day * 86400000, value: counts.get(day) || 0 })
  return out
}

// Governance events are the ones a reviewer cares about; logins and integration pings are context.
export const GOVERNANCE_EVENTS = /^(APPROVAL_|ADVISORY_|GOVERNED_|EVIDENCE_|PREFLIGHT_)/
export const humanizeEvent = type => (type || '').toLowerCase().replaceAll('_', ' ').replace(/^\w/, c => c.toUpperCase())
