// eRTMAC-NWIS domain model: API paths, tolerant normalizers and display maths. Pure and testable.
// The backend owns every number (distances, scores, probabilities); this module only shapes and formats them.

export const SYNTHETIC = 'synthetic_demo'
export const RADIUS_PRESETS_KM = [2, 5, 10, 20]
export const LOOKAHEAD_M = [50, 100, 150]

// Normalized hazard/event taxonomy (master report §34). Unknown labels still render, humanized.
export const HAZARDS = {
  stuck_pipe: 'Stuck pipe',
  mud_loss: 'Mud loss',
  kick_or_overpressure: 'Kick / overpressure',
  torque_drag: 'Torque / drag',
  tight_hole: 'Tight hole',
  hydraulic_anomaly: 'Hydraulic anomaly',
  cementing_issue: 'Cementing issue',
  fishing: 'Fishing',
  npt: 'NPT',
  wellbore_instability: 'Wellbore instability',
}
export const PRIMARY_HAZARDS = ['stuck_pipe', 'mud_loss', 'kick_or_overpressure', 'torque_drag']
export const humanize = value => String(value ?? '').replaceAll('_', ' ').replace(/^\w/, c => c.toUpperCase())
export const hazardLabel = type => HAZARDS[type] || humanize(type)

// Offset similarity components (report §52). The UI shows every one; ranking is never hidden.
export const SCORE_COMPONENTS = [
  ['geographic', 'Geographic'],
  ['formation', 'Formation'],
  ['depth', 'Depth overlap'],
  ['trajectory', 'Trajectory'],
  ['program', 'Program / context'],
  ['data_quality', 'Data quality'],
]

export const AUDIT_EVENTS = {
  report_ingested: 'Report ingested',
  event_extracted: 'Event extracted',
  event_validated: 'Event validated',
  offset_query: 'Offset query',
  risk_assessment: 'Risk assessment',
  alert_created: 'Alert created',
  alert_acknowledged: 'Alert acknowledged',
  advisory_reviewed: 'Advisory reviewed',
}
export const auditLabel = type => AUDIT_EVENTS[String(type).toLowerCase()] || humanize(String(type).toLowerCase())
export const isNwisAudit = type => Object.hasOwn(AUDIT_EVENTS, String(type).toLowerCase())

// Audit details for display: secrets, hashes and filesystem paths are never shown.
const HIDDEN_KEY = /(path|file|secret|token|password|credential|hash|key)$/i
const LOOKS_LIKE_PATH = /^(?:[A-Za-z]:[\\/]|\/(?:home|usr|var|etc|tmp|mnt|opt|srv|data)\b)/
export function safeDetails(details) {
  if (!details || typeof details !== 'object') return []
  return Object.entries(details).filter(([key]) => !HIDDEN_KEY.test(key)).map(([key, value]) => {
    const text = Array.isArray(value) ? value.join(', ') : value && typeof value === 'object' ? JSON.stringify(value) : String(value)
    return [humanize(key), LOOKS_LIKE_PATH.test(text) ? '[path hidden]' : text.slice(0, 160)]
  })
}

// ── API paths (same-origin /api prefix is added by services/api.js) ──
export function qs(params = {}) {
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : String(v)])
  const text = new URLSearchParams(entries).toString()
  return text ? `?${text}` : ''
}
const enc = encodeURIComponent
export const paths = {
  wells: (params = {}) => `/wells${qs({ limit: 200, ...params })}`,
  well: id => `/wells/${enc(id)}`,
  nearby: (id, params = {}) => `/wells/${enc(id)}/nearby${qs(params)}`,
  correlation: (id, params = {}) => `/wells/${enc(id)}/correlation${qs(params)}`,
  events: (params = {}) => `/events${qs({ limit: 100, ...params })}`,
  risk: (id, lookahead) => `/wells/${enc(id)}/risk${qs({ lookahead_m: lookahead })}`,
  telemetry: (id, params = {}) => `/wells/${enc(id)}/telemetry${qs(params)}`,
  query: '/query',
  advisories: (params = {}) => `/advisories${qs(params)}`,
  advisoryReview: id => `/advisories/${enc(id)}/review`,
  audit: (params = {}) => `/audit/log${qs({ limit: 100, ...params })}`,
}

// ── Normalizers: accept a bare array or a paginated envelope; never invent missing values ──
export const listOf = data => (Array.isArray(data) ? data : data?.items ?? data?.results ?? [])
export const num = value => (typeof value === 'number' && Number.isFinite(value) ? value : null)
export const isSynthetic = data => data?.dataset_origin === SYNTHETIC || listOf(data).some(item => item?.dataset_origin === SYNTHETIC)

export function normalizeOffset(item) {
  const well = item.well || item
  const components = item.components || item.component_scores || {}
  return {
    id: well.id ?? item.well_id,
    name: well.name ?? well.id ?? item.well_id,
    well,
    distanceKm: num(item.distance_km),
    total: num(item.total_score ?? item.score),
    rank: num(item.rank),
    components: Object.fromEntries(SCORE_COMPONENTS.map(([key]) => [key, num(components[key])])),
    eventCounts: item.event_counts || {},
    formationAtDepth: item.formation_at_depth ?? null,
    note: item.note ?? null,
  }
}

// Backend order is authoritative; `rank` falls back to it.
export function rankedOffsets(data) {
  return listOf(data).map(normalizeOffset).map((offset, index) => ({ ...offset, rank: offset.rank ?? index + 1 }))
}

// "Why is the closest well not the best analog?" Uses only backend distances and scores.
export function closestExplanation(offsets) {
  const withDistance = offsets.filter(o => o.distanceKm != null)
  if (withDistance.length < 2) return null
  const closest = withDistance.reduce((a, b) => (b.distanceKm < a.distanceKm ? b : a))
  if (closest.rank === 1) return null
  const weakest = SCORE_COMPONENTS.filter(([key]) => key !== 'geographic' && closest.components[key] != null)
    .sort(([a], [b]) => closest.components[a] - closest.components[b]).slice(0, 2)
    .map(([key, label]) => ({ key, label, value: closest.components[key] }))
  return { closest, top: offsets.find(o => o.rank === 1) || offsets[0], weakest }
}

export function normalizeHazard(h) {
  const probability = num(h.probability)
  return {
    type: h.type ?? h.hazard,
    probability,
    confidence: num(h.confidence),
    trend: h.trend ?? null,
    severity: h.severity ?? null,
    series: Array.isArray(h.trend_series) ? h.trend_series.filter(p => num(p?.probability) != null) : [],
    wells: h.supporting_offset_wells || [],
    factors: h.top_factors || [],
    evidenceIds: h.evidence_ids || [],
    evidenceCount: num(h.evidence_count) ?? (h.evidence_ids?.length || 0),
    historical: num(h.historical_contribution),
    telemetry: num(h.telemetry_contribution),
    freshnessS: num(h.data_freshness_s),
    telemetryFeatures: h.telemetry_features || [],
    missing: h.missing_evidence || [],
    confidenceNote: h.confidence_explanation ?? null,
    advisoryId: h.advisory_id ?? null,
  }
}

// Level describes probability only. Red is reserved for backend-declared critical severity.
export function riskLevel(hazard) {
  if (hazard.severity === 'critical') return 'critical'
  if (hazard.probability == null) return 'unknown'
  return hazard.probability >= 0.6 ? 'high' : hazard.probability >= 0.3 ? 'elevated' : 'low'
}

export function freshness(asOf, now = Date.now(), staleAfterS = 120) {
  const t = Date.parse(asOf)
  if (!Number.isFinite(t)) return { state: 'unknown', ageS: null }
  const ageS = Math.max(0, Math.round((now - t) / 1000))
  return { state: ageS > staleAfterS ? 'stale' : 'fresh', ageS }
}

// Telemetry: one series per channel the backend declares AND actually has values for. Never fabricate channels.
export function telemetrySeries(data) {
  const samples = data?.samples || []
  return (data?.channels || []).map(channel => ({
    id: channel.mnemonic,
    label: channel.label || channel.mnemonic,
    unit: channel.unit || '',
    quality: channel.quality ?? null,
    points: samples.map(s => ({ t: Date.parse(s.t ?? s.time), v: s.values?.[channel.mnemonic], md: num(s.md_m) }))
      .filter(p => Number.isFinite(p.t) && typeof p.v === 'number' && Number.isFinite(p.v)),
  })).filter(series => series.points.length)
}

export function groupResults(data) {
  const groups = { well: [], event: [], report: [] }
  for (const item of listOf(data?.results ? data.results : data)) {
    const kind = item.kind in groups ? item.kind : 'report'
    groups[kind].push(item)
  }
  return groups
}

// Count events by formation × hazard for the dashboard distribution.
export function eventMatrix(events) {
  const formations = [...new Set(events.map(e => e.formation || 'Unassigned'))]
  const types = [...new Set(events.map(e => e.type))]
  const counts = Object.fromEntries(formations.map(f => [f, Object.fromEntries(types.map(t => [t, 0]))]))
  for (const e of events) counts[e.formation || 'Unassigned'][e.type] += 1
  return { formations, types, counts }
}

// ── Correlation depth maths ──
export function depthRange(tracks, window, pad = 0.04) {
  const values = tracks.flatMap(t => [...(t.formations || []).flatMap(f => [f.top, f.base]), ...(t.events || []).map(e => e.depth)])
    .concat(window ? [window.top, window.base] : []).filter(v => num(v) != null)
  if (!values.length) return null
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1
  return [Math.max(0, min - span * pad), max + span * pad]
}
export const depthToY = (depth, [min, max], top, height) => top + ((depth - min) / (max - min || 1)) * height

// Formation tops shared by adjacent tracks, for dashed "interpreted correlation" connectors.
export function sharedTops(left, right) {
  const tops = new Map((right.formations || []).map(f => [f.name, f.top]))
  return (left.formations || []).filter(f => tops.has(f.name)).map(f => ({ name: f.name, from: f.top, to: tops.get(f.name) }))
}

// ── Formatting ──
const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
export const fmtM = value => (num(value) == null ? '—' : `${nf0.format(value)} m`)
export const fmtKm = value => (num(value) == null ? '—' : `${value < 10 ? value.toFixed(1) : Math.round(value)} km`)
export const fmtPct = value => (num(value) == null ? '—' : `${Math.round(value * 100)}%`)
export const fmtScore = value => (num(value) == null ? '—' : value.toFixed(2))
export function fmtAge(seconds) {
  if (num(seconds) == null) return 'unknown'
  if (seconds < 90) return `${seconds} s ago`
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`
  return `${Math.round(seconds / 3600)} h ago`
}
