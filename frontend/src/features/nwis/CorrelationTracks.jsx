import { useEffect, useMemo, useRef, useState } from 'react'
import { niceTicks } from '../insights/insightsModel.js'
import { depthToY, fmtM, fmtPct, hazardLabel, humanize, sharedTops } from './nwisModel.js'
import { DrillingEventChip, VerificationBadge } from './components.jsx'

// Synchronized depth tracks: active well + selected offsets on one vertical depth axis (TVD preferred).
// Formation-top connectors are dashed and labelled as interpretation: distance never implies continuity.
const FORMATION_TONES = ['#d8e4f2', '#e6e0f3', '#dcefe6', '#f3e7d6', '#e2e8ee', '#efdede']
const tone = (name, names) => FORMATION_TONES[names.indexOf(name) % FORMATION_TONES.length]

function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(720)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(300, Math.round(entry.contentRect.width))))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

export default function CorrelationTracks({ data, height = 620 }) {
  const [ref, width] = useWidth()
  const [focus, setFocus] = useState('window')
  const [selected, setSelected] = useState(null)
  const tracks = useMemo(() => data?.tracks || [], [data])
  const window = data?.lookahead_window
  const current = data?.current_depth_m
  const unit = String(data?.depth_ref || 'tvd').toUpperCase()
  const names = useMemo(() => [...new Set(tracks.flatMap(t => (t.formations || []).map(f => f.name)))], [tracks])

  const range = useMemo(() => {
    const all = tracks.flatMap(t => [...(t.formations || []).flatMap(f => [f.top, f.base]), ...(t.events || []).map(e => e.depth)]).filter(Number.isFinite)
    if (!all.length) return null
    if (focus === 'window' && Number.isFinite(current) && window) return [Math.max(0, current - 420), window.base + 380]
    return [Math.max(0, Math.min(...all) - 50), Math.max(...all) + 50]
  }, [tracks, focus, current, window])

  if (!tracks.length || !range) return <p className="chart-empty">No correlation tracks returned.</p>
  const axis = 58, top = 34, plotH = height - top - 12, gap = width < 560 ? 12 : 34
  const trackW = Math.max(40, (width - axis - gap * (tracks.length - 1)) / tracks.length)
  const x = i => axis + i * (trackW + gap)
  const y = d => depthToY(Math.min(Math.max(d, range[0]), range[1]), range, top, plotH)
  const inRange = d => d >= range[0] && d <= range[1]
  const ticks = niceTicks(range[0], range[1], 7).filter(inRange)
  const pick = (track, event) => setSelected({ track, event })

  return <figure className="nw-correlation">
    <div className="nw-corr-toolbar">
      <div className="nw-segmented" role="group" aria-label="Depth range"><span className="nw-seg-label" aria-hidden="true">Range</span>
        <button type="button" aria-pressed={focus === 'window'} onClick={() => setFocus('window')}>Around look-ahead</button>
        <button type="button" aria-pressed={focus === 'full'} onClick={() => setFocus('full')}>Full well</button></div>
      <p className="muted small">Vertical axis: {unit} (m). Dashed connectors are interpreted formation-top correlations, not proven continuity.</p>
    </div>
    <div ref={ref} className="nw-corr-canvas">
      <svg width={width} height={height} role="img" aria-label={`Formation correlation by ${unit}: ${tracks.map(t => t.name || t.well_id).join(', ')}. Details are in the table below.`}>
        <defs><pattern id="nw-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="rgba(60,80,110,0.28)" strokeWidth="2" /></pattern></defs>
        {ticks.map(t => <g key={t} className="nw-corr-grid"><line x1={axis - 6} x2={width} y1={y(t)} y2={y(t)} /><text x={axis - 10} y={y(t)} dy="0.32em" textAnchor="end">{t}</text></g>)}
        <text className="nw-corr-unit" x={4} y={14}>{unit} m</text>
        {tracks.slice(0, -1).map((track, i) => sharedTops(track, tracks[i + 1]).filter(s => inRange(s.from) && inRange(s.to)).map(s =>
          <line key={`${i}-${s.name}`} className="nw-corr-link" x1={x(i) + trackW} x2={x(i + 1)} y1={y(s.from)} y2={y(s.to)} />))}
        {tracks.map((track, i) => <g key={track.well_id} className="nw-corr-track" data-role={track.role}>
          <text className="nw-corr-name" x={x(i) + trackW / 2} y={20} textAnchor="middle">{track.name || track.well_id}</text>
          <rect className="nw-corr-frame" x={x(i)} y={top} width={trackW} height={plotH} />
          {(track.formations || []).filter(f => f.base > range[0] && f.top < range[1]).map(f => <g key={f.name}>
            <rect x={x(i)} y={y(f.top)} width={trackW} height={Math.max(1, y(f.base) - y(f.top))} fill={tone(f.name, names)} />
            {f.interpreted && <rect x={x(i)} y={y(f.top)} width={trackW} height={Math.max(1, y(f.base) - y(f.top))} fill="url(#nw-hatch)" />}
            {inRange(f.top) && <line className={`nw-corr-top${f.interpreted ? ' is-interpreted' : ''}`} x1={x(i)} x2={x(i) + trackW} y1={y(f.top)} y2={y(f.top)} />}
            {y(f.base) - y(f.top) > 16 && trackW > 70 && <text className="nw-corr-fm" x={x(i) + 5} y={Math.max(y(f.top), top) + 13}>{f.name}{f.confidence == null ? ' ?' : ''}</text>}
          </g>)}
          {Number.isFinite(track.td_tvd_m) && track.td_tvd_m < range[1] && <g className="nw-corr-td"><rect x={x(i)} y={y(track.td_tvd_m)} width={trackW} height={top + plotH - y(track.td_tvd_m)} />
            {trackW > 70 && <text x={x(i) + trackW / 2} y={y(track.td_tvd_m) + 14} textAnchor="middle">TD {Math.round(track.td_tvd_m)}</text>}</g>}
          {(track.casing || []).filter(c => inRange(c.depth)).map(c => <g key={c.size} className="nw-corr-casing"><path d={`M${x(i) + trackW} ${y(c.depth)} l-8 -8 v8 z`} /><title>{`${c.size} casing shoe at ${Math.round(c.depth)} m`}</title></g>)}
          {track.role === 'active' && Number.isFinite(current) && <line className="nw-corr-bit" x1={x(i) - 4} x2={x(i) + trackW + 4} y1={y(current)} y2={y(current)} />}
          {(track.events || []).filter(e => inRange(e.depth)).map(e => <g key={e.id} className="nw-corr-event" data-type={e.type} data-severity={e.severity} data-unverified={e.verification && e.verification !== 'verified' ? 'true' : undefined}
            tabIndex={0} role="button" aria-pressed={selected?.event.id === e.id} aria-label={`${track.well_id} ${hazardLabel(e.type)} at ${Math.round(e.depth)} m ${unit}, ${e.severity} severity`}
            onClick={() => pick(track, e)} onKeyDown={ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(track, e) } }}>
            <circle cx={x(i) + trackW - 14} cy={y(e.depth)} r={e.severity === 'high' ? 7 : 5.5} /><title>{`${hazardLabel(e.type)} · ${Math.round(e.depth)} m`}</title></g>)}
        </g>)}
        {window && <g className="nw-corr-window"><rect x={axis} width={width - axis} y={y(window.top)} height={Math.max(2, y(window.base) - y(window.top))} />
          <text x={width - 6} y={y(window.base) - 5} textAnchor="end">Look-ahead +{data.lookahead_m} m</text></g>}
        {Number.isFinite(current) && <text className="nw-corr-bit-label" x={axis + 4} y={y(current) - 5}>Bit {Math.round(current)} m {unit}</text>}
      </svg>
    </div>
    <div className="nw-corr-detail" aria-live="polite">{selected ? <>
      <DrillingEventChip type={selected.event.type} severity={selected.event.severity} /> <strong>{selected.track.well_id}</strong> · {fmtM(selected.event.depth)} {unit} · {humanize(selected.event.severity)} · confidence {fmtPct(selected.event.confidence)} <VerificationBadge state={selected.event.verification} />
      {selected.event.summary && <blockquote>“{selected.event.summary}”</blockquote>}</> : <span className="muted">Select an event marker (click or Enter) to read its source wording.</span>}</div>
    <p className="nw-corr-legend muted small"><span className="lg-window" />Look-ahead window <span className="lg-bit" />Current bit depth <span className="lg-hatch" />Interpreted / low-confidence interval <span className="lg-td" />Below TD (no data) · ◣ casing shoe · “?” formation top unknown · hollow marker = unverified event</p>
    <details className="chart-data"><summary>View correlation as a table</summary>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Correlation data"><table><thead><tr><th>Well</th><th>Formation</th><th>Top ({unit})</th><th>Base ({unit})</th><th>Confidence</th><th>Events in interval</th></tr></thead>
        <tbody>{tracks.flatMap(t => (t.formations || []).map(f => <tr key={`${t.well_id}-${f.name}`}><td>{t.well_id}</td><td>{f.name}{f.interpreted ? ' (interpreted)' : ''}</td><td className="num">{Math.round(f.top)}</td><td className="num">{Math.round(f.base)}</td><td className="num">{f.confidence == null ? 'unknown' : fmtPct(f.confidence)}</td>
          <td>{(t.events || []).filter(e => e.depth >= f.top && e.depth < f.base).map(e => `${hazardLabel(e.type)} @ ${Math.round(e.depth)}`).join('; ') || '—'}</td></tr>))}</tbody></table></div>
    </details>
  </figure>
}
