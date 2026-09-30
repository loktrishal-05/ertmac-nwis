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

// Backend NWIS audit actions (payload.action on GET /api/audit).
export const AUDIT_EVENTS = {
  terms_accepted: 'NWIS terms accepted',
  report_ingested: 'Report ingested',
  drilling_lesson_validation: 'Event validated / rejected',
  knowledge_query: 'Evidence query',
  risk_assessed: 'Risk assessment recorded',
  advisory_review: 'Advisory reviewed',
}
// Hazard types the backend accepts as event filters (Hazard literal in the B2 schema).
export const EVENT_TYPES = ['mud_loss', 'stuck_pipe', 'kick_or_overpressure', 'torque_drag', 'cementing_issue', 'fishing', 'npt']
// B2 records reviewer / actor as a user id. Only the signed-in user's own name is known to the browser (from /auth/me);
// anyone else is shown by a shortened id rather than a raw UUID. No extra lookup contract is assumed.
export function personLabel(id, me) {
  if (id == null || id === '') return null
  if (me?.id != null && String(me.id) === String(id)) return `${me.display_name || me.username || 'you'} (you)`
  return `user ${String(id).slice(0, 8)}`
}
export const auditLabel = type => AUDIT_EVENTS[String(type).toLowerCase()] || humanize(String(type).toLowerCase())

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
  wells: (params = {}) => `/wells${qs({ limit: 100, ...params })}`,
  terms: '/terms',
  termsAccept: '/terms/accept',
  formations: id => `/wells/${enc(id)}/formations?limit=100`,
  assess: (id, lookahead) => `/wells/${enc(id)}/assess${qs({ lookahead_m: lookahead })}`,
  assessment: id => `/assessments/${enc(id)}`,
  well: id => `/wells/${enc(id)}`,
  nearby: (id, params = {}) => `/wells/${enc(id)}/nearby${qs(params)}`,
  correlation: (id, params = {}) => `/wells/${enc(id)}/correlation${qs(params)}`,
  events: (params = {}) => `/events${qs({ limit: 100, ...params })}`,
  risk: (id, lookahead) => `/wells/${enc(id)}/risk${qs({ lookahead_m: lookahead })}`,
  telemetry: (id, params = {}) => `/wells/${enc(id)}/telemetry${qs(params)}`,
  query: '/query',
  advisories: (params = {}) => `/advisories${qs(params)}`,
  advisoryReview: id => `/advisories/${enc(id)}/review`,
  audit: (params = {}) => `/audit${qs({ limit: 100, ...params })}`,
  auditVerify: '/audit/verify',
}

// ── Normalizers: accept a bare array or a paginated envelope; never invent missing values ──
export const listOf = data => (Array.isArray(data) ? data : data?.items ?? data?.results ?? [])
export const num = value => (typeof value === 'number' && Number.isFinite(value) ? value : null)
export const isSynthetic = data => data?.dataset_origin === SYNTHETIC || listOf(data).some(item => item?.dataset_origin === SYNTHETIC)



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


// Level describes probability only. Red is reserved for backend-declared critical severity.
export function riskLevel(hazard) {
  if (hazard.severity === 'critical') return 'critical'
  if (hazard.probability == null) return 'unknown'
  return hazard.probability >= 0.6 ? 'high' : hazard.probability >= 0.3 ? 'elevated' : 'low'
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
const nf2 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
export const fmtValue = value => (num(value) == null ? '—' : nf2.format(value))
