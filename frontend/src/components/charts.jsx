import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { niceTicks } from '../features/insights/insightsModel.js'

// Hand-built SVG charts: live data only, readable at a glance, operable by pointer and keyboard,
// and always backed by a plain data table for assistive tech and verification.

function useWidth(fallback = 640) {
  const ref = useRef(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

const number = (value, digits = 2) => (Number.isInteger(value) ? String(value) : String(+value.toFixed(digits)))

function timeFormatter(span) {
  const day = 86400000
  if (span < 2 * day) return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })
  if (span < 400 * day) return new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
  return new Intl.DateTimeFormat(undefined, { month: 'short', year: 'numeric' })
}
const fullTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const nearestPoint = (points, t) => points.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a))

export function TimeSeriesChart({ series = [], unit = '', height = 260, label, emptyText = 'No readings returned.', threshold = null }) {
  const [ref, width] = useWidth()
  const gradientBase = useId().replaceAll(':', '')
  const [cursor, setCursor] = useState(null) // index into the primary series
  const visible = useMemo(() => series.filter(s => s.points.length), [series])
  const primary = visible[0]
  const pad = { top: 26, right: 16, bottom: 30, left: 46 }
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom

  const model = useMemo(() => {
    const all = visible.flatMap(s => s.points)
    if (!all.length) return null
    const t0 = Math.min(...all.map(p => p.t)), t1 = Math.max(...all.map(p => p.t))
    const values = all.map(p => p.v).concat(Number.isFinite(threshold) ? [threshold] : [])
    const v0 = Math.min(...values), v1 = Math.max(...values)
    const ticks = niceTicks(v0 - (v1 - v0) * 0.08, v1 + (v1 - v0) * 0.08, 4)
    const yMin = ticks[0], yMax = ticks[ticks.length - 1]
    const x = t => 46 + (t1 === t0 ? plotW / 2 : ((t - t0) / (t1 - t0)) * plotW)
    const y = v => 26 + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH
    const count = Math.max(2, Math.min(6, Math.floor(plotW / 120)))
    const xTicks = t1 === t0 ? [t0] : Array.from({ length: count }, (_, i) => t0 + ((t1 - t0) * i) / (count - 1))
    return { ticks, x, y, format: timeFormatter(t1 - t0), xTicks }
  }, [visible, plotW, plotH, threshold])

  if (!model) return <p className="chart-empty">{emptyText}</p>
  const { ticks, x, y, format, xTicks } = model
  const line = points => points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join('')
  const area = points => `${line(points)}L${x(points[points.length - 1].t).toFixed(1)},${pad.top + plotH}L${x(points[0].t).toFixed(1)},${pad.top + plotH}Z`
  const active = cursor != null ? primary?.points[cursor] : null
  const nearestIndex = clientX => {
    const px = clientX - ref.current.getBoundingClientRect().left
    let best = 0
    primary.points.forEach((p, i) => { if (Math.abs(x(p.t) - px) < Math.abs(x(primary.points[best].t) - px)) best = i })
    return best
  }
  const onKey = event => {
    const last = primary.points.length - 1
    const next = { ArrowRight: Math.min(last, (cursor ?? -1) + 1), ArrowLeft: Math.max(0, (cursor ?? last + 1) - 1), Home: 0, End: last }[event.key]
    if (next != null) { event.preventDefault(); setCursor(next) }
    if (event.key === 'Escape') setCursor(null)
  }
  const tipLeft = active ? Math.min(Math.max(x(active.t), 96), width - 96) : 0

  return <figure className="chart">
    <div ref={ref} className="chart-canvas" tabIndex={0} role="group" aria-roledescription="chart"
      aria-label={`${label}. Use the arrow keys to read values.`} onKeyDown={onKey}
      onPointerMove={event => setCursor(nearestIndex(event.clientX))} onPointerLeave={() => setCursor(null)} onBlur={() => setCursor(null)}>
      <svg width={width} height={height} aria-hidden="true">
        <defs>{visible.map((s, i) => <linearGradient key={s.id} id={`${gradientBase}-${i}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={s.color} stopOpacity="0.2" /><stop offset="100%" stopColor={s.color} stopOpacity="0" /></linearGradient>)}</defs>
        {ticks.map(tick => <g key={tick} className="chart-grid"><line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
          <text x={pad.left - 10} y={y(tick)} dy="0.32em" textAnchor="end">{number(tick)}</text></g>)}
        {unit && <text className="chart-unit" x={pad.left - 10} y={10} textAnchor="end">{unit}</text>}
        {Number.isFinite(threshold) && <g className="chart-threshold"><line x1={pad.left} x2={width - pad.right} y1={y(threshold)} y2={y(threshold)} />
          <text x={pad.left + 6} y={y(threshold) - 6}>Your threshold · {number(threshold)} {unit}</text></g>}
        {xTicks.map((t, i) => <text key={i} className="chart-axis" x={x(t)} y={height - 8} textAnchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'}>{format.format(t)}</text>)}
        {visible.map((s, i) => <g key={s.id}>
          <path className="chart-area" d={area(s.points)} fill={`url(#${gradientBase}-${i})`} />
          <path className={`chart-line${i ? ' is-secondary' : ''}`} d={line(s.points)} stroke={s.color} pathLength="1" />
        </g>)}
        {active && <g className="chart-cursor">
          <line x1={x(active.t)} x2={x(active.t)} y1={pad.top} y2={pad.top + plotH} />
          {visible.map(s => { const p = nearestPoint(s.points, active.t); return <circle key={s.id} cx={x(p.t)} cy={y(p.v)} r="4.5" stroke={s.color} /> })}
        </g>}
      </svg>
      {active && <div className="chart-tip" style={{ left: tipLeft }} role="status">
        <time>{fullTime.format(active.t)}</time>
        {visible.map(s => { const p = nearestPoint(s.points, active.t); return <span key={s.id}><i style={{ background: s.color }} />{s.label}<strong>{number(p.v)} {unit}</strong></span> })}
      </div>}
    </div>
    <details className="chart-data"><summary>View readings as a table</summary>
      <div className="table-scroll" tabIndex={0} role="region" aria-label={`${label} data`}><table><thead><tr><th>Series</th><th>Time</th><th>Value</th><th>Source</th></tr></thead>
        <tbody>{visible.flatMap(s => s.points.map((p, i) => <tr key={`${s.id}-${i}`}><td>{s.label}</td><td>{fullTime.format(p.t)}</td><td className="num">{number(p.v)} {unit}</td><td>{p.source ? `${p.source}${p.row ? ` · row ${p.row}` : ''}` : '—'}</td></tr>))}</tbody></table></div>
    </details>
  </figure>
}

export function ColumnChart({ data = [], height = 150, label, format = v => v, unitLabel = 'events' }) {
  const [ref, width] = useWidth(480)
  const [hover, setHover] = useState(null)
  if (!data.length) return <p className="chart-empty">Nothing recorded yet.</p>
  const top = 10, bottom = 24, plotH = height - top - bottom
  const max = Math.max(1, ...data.map(d => d.value))
  const gap = Math.max(3, Math.min(10, width / data.length / 4))
  const barW = Math.max(4, (width - gap * (data.length - 1)) / data.length)
  const every = Math.ceil(data.length / Math.max(2, Math.floor(width / 70)))
  const shown = hover != null ? data[hover] : null
  return <figure className="chart">
    <div ref={ref} className="chart-canvas" onPointerLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label={`${label}: ${data.map(d => `${format(d.t)} ${d.value}`).join(', ')}`}>
        <line className="chart-baseline" x1="0" x2={width} y1={top + plotH} y2={top + plotH} />
        {data.map((d, i) => { const h = Math.max(d.value ? 3 : 0, (d.value / max) * plotH); const bx = i * (barW + gap)
          return <g key={i} onPointerEnter={() => setHover(i)}>
            <rect className="chart-hit" x={bx - gap / 2} y={top} width={barW + gap} height={plotH} />
            <rect className={`chart-bar${hover === i ? ' is-active' : ''}`} x={bx} y={top + plotH - h} width={barW} height={h} rx={Math.min(4, barW / 2)} style={{ '--i': i }} />
            {i % every === 0 && <text className="chart-axis" x={bx + barW / 2} y={height - 6} textAnchor="middle">{format(d.t)}</text>}
          </g> })}
      </svg>
      {shown && <div className="chart-tip" style={{ left: Math.min(Math.max(hover * (barW + gap) + barW / 2, 70), width - 70) }} role="status">
        <time>{format(shown.t)}</time><span><strong>{shown.value} {unitLabel}</strong></span></div>}
    </div>
  </figure>
}

export function BarList({ data = [], label, unitLabel = '', limit = 8 }) {
  if (!data.length) return <p className="chart-empty">Nothing recorded yet.</p>
  const max = Math.max(...data.map(d => d.value))
  return <ul className="bar-list" aria-label={label}>{data.slice(0, limit).map((d, i) =>
    <li key={d.label} style={{ '--w': `${(d.value / max) * 100}%`, '--i': i }}>
      <span className="bar-list-label">{d.label}</span><span className="bar-list-track" aria-hidden="true"><span className="bar-list-fill" style={d.color ? { background: d.color } : undefined} /></span>
      <span className="bar-list-value">{d.value}{unitLabel && <small> {unitLabel}</small>}</span>
    </li>)}</ul>
}
