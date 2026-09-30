// NWIS B2 API → view-model adapters: the ONLY place that knows raw backend field names.
// Screens read the stable view-model shapes returned here (docs/nwis/frontend_api_contract.md).
// Rules: numbers are finite or null (never coerced to 0); strings are non-empty or null; lists are arrays.
// Nothing here computes distances, rankings or probabilities: it only renames, groups and formats backend values.
import { SCORE_COMPONENTS, listOf, num } from './nwisModel.js'

const str = value => (typeof value === 'string' && value.trim() ? value : null)
const arr = value => (Array.isArray(value) ? value : [])
const pick = (obj, ...keys) => { for (const key of keys) { const value = obj?.[key]; if (value !== undefined && value !== null) return value } return null }
const ids = list => arr(list).map(item => (typeof item === 'string' ? item : str(item?.id) ?? str(item?.well_id) ?? str(item?.event_id))).filter(Boolean)
const origin = (...sources) => sources.map(s => str(s?.dataset_origin)).find(Boolean) ?? null
const fixed = (value, digits = 2) => (num(value) == null ? null : value.toFixed(digits))

// B2 lists: { items, limit, offset, has_more, as_of } — there is no total.
function envelope(data, adapt, extra = {}) {
  const items = listOf(data).map(adapt)
  return { items, total: num(data?.total), has_more: data?.has_more === true, as_of: str(data?.as_of), dataset_origin: str(data?.dataset_origin), ...extra }
}

// ── Well (B2 WellOut: latitude, longitude, current_md, total_depth_md; no formation/TVD — those come from risk) ──
export function adaptFormation(f) {
  const confidence = num(f?.confidence)
  return { name: str(pick(f, 'formation', 'name')), top: num(pick(f, 'top', 'top_tvd', 'top_md')), base: num(pick(f, 'base', 'bottom_tvd', 'bottom_md')),
    confidence, interpreted: f?.interpreted === true || (confidence != null && confidence < 0.6), available: f?.alignment_available !== false }
}
export function adaptWell(w) {
  const id = str(pick(w, 'id', 'well_id', 'offset_well_id'))
  const status = str(w?.status)
  return {
    id, name: str(pick(w, 'name', 'well_name')) ?? id, field: str(w?.field), operator: str(w?.operator), status,
    role: str(w?.role) ?? (status && /^active$/i.test(status) ? 'active' : null),
    lat: num(pick(w, 'latitude', 'lat')), lon: num(pick(w, 'longitude', 'lon')),
    well_type: str(w?.well_type), trajectory_type: str(w?.trajectory_type), trajectory_summary: str(w?.trajectory_summary), spud_date: str(w?.spud_date),
    td_md_m: num(pick(w, 'total_depth_md', 'td_md_m')), td_tvd_m: num(w?.td_tvd_m), data_quality: num(w?.data_quality),
    current_md_m: num(pick(w, 'current_md', 'current_md_m')), current_tvd_m: num(w?.current_tvd_m), current_tvdss_m: num(w?.current_tvdss_m),
    current_formation: str(w?.current_formation), hole_section: str(w?.hole_section), note: str(w?.note),
    formations: arr(w?.formations).map(adaptFormation), upcoming_formations: [], casing: [],
    as_of: str(w?.as_of), dataset_origin: origin(w),
  }
}
export const adaptWellList = data => envelope(data, adaptWell)
// GET /api/wells/{id}/formations (FormationOut: formation, top_md…, top_tvd…, confidence).
export const adaptFormationList = data => envelope(data, f => ({ name: str(f?.formation), top_md: num(f?.top_md), base_md: num(f?.bottom_md),
  top: num(f?.top_tvd), base: num(f?.bottom_tvd), top_tvdss: num(f?.top_tvdss), base_tvdss: num(f?.bottom_tvdss), confidence: num(f?.confidence), source: str(f?.source) }))

// ── NearbyWell (B2 MatchOut is flat; backend order is the ranking) ──
export function normalizeOffset(item) {
  const nested = item?.well ? adaptWell(item.well) : null
  const id = str(item?.offset_well_id) ?? nested?.id ?? null
  const legacy = item?.components || item?.component_scores || {}
  return {
    id, name: nested?.name ?? id, well: nested ?? { id, name: id },
    distanceKm: num(item?.distance_km) ?? (num(item?.distance_m) == null ? null : item.distance_m / 1000), total: num(item?.total_score ?? item?.score), rank: num(item?.rank),
    components: Object.fromEntries(SCORE_COMPONENTS.map(([key]) => [key, num(item?.[`${key}_score`]) ?? num(legacy[key])])),
    depthBasis: str(item?.depth_basis), explanation: arr(item?.explanation).filter(s => typeof s === 'string'),
    // B2 MatchOut carries no event counts; null = unknown (useNearby fills it from /api/events).
    eventCounts: item?.event_counts ? Object.fromEntries(Object.entries(item.event_counts).filter(([, n]) => num(n) != null)) : null,
    formationAtDepth: str(item?.formation_at_depth), note: str(item?.note), dataset_origin: origin(item, nested),
  }
}
export const rankedOffsets = data => listOf(data).map(normalizeOffset).map((offset, index) => ({ ...offset, rank: offset.rank ?? index + 1 }))
export function adaptNearby(data) {
  const items = rankedOffsets(data)
  const weights = listOf(data)[0]?.weights ?? data?.weights ?? null
  return { items, has_more: data?.has_more === true, weights: weights && typeof weights === 'object' ? weights : null, formula: str(data?.formula),
    as_of: str(data?.as_of), dataset_origin: str(data?.dataset_origin) ?? items[0]?.dataset_origin ?? null }
}

// ── DrillingEvent (B2 EventOut) ──
export function adaptEvent(e) {
  const reportId = str(e?.source_report_id) ?? str(e?.source?.report_id)
  const page = num(e?.source_page) ?? num(e?.source?.page)
  return {
    id: str(e?.id), well_id: str(e?.well_id), type: str(pick(e, 'event_type', 'type')),
    observation: str(e?.observation), raw_observation: str(pick(e, 'raw_phrase', 'raw_observation')) ?? str(e?.observation),
    depth_md_m: num(pick(e, 'start_depth_md', 'depth_md_m')), depth_md_end_m: num(e?.end_depth_md),
    depth_tvd_m: num(pick(e, 'tvd', 'depth_tvd_m')), depth_tvdss_m: num(pick(e, 'tvdss', 'depth_tvdss_m')), formation: str(e?.formation),
    severity: str(e?.severity), cause: str(e?.cause), npt_hours: num(e?.npt_hours), mitigation: str(e?.mitigation), outcome: str(e?.outcome),
    confidence: num(e?.confidence), verification: str(pick(e, 'verification_state', 'verification')),
    source: reportId || page != null ? { report_id: reportId, page, title: str(e?.source?.title), url: reportId ? `/api/reports/${encodeURIComponent(reportId)}/source${page != null ? `#page=${page}` : ''}` : null } : null,
    dataset_origin: origin(e),
  }
}
export const adaptEventList = data => envelope(data, adaptEvent)
const eventDepth = (event, basis) => (basis === 'tvdss' ? event.depth_tvdss_m : basis === 'tvd' ? event.depth_tvd_m : event.depth_md_m)

// ── FormationCorrelation (B2: alignment_basis TVDSS → TVD → MD, tracks, current_bit_depth, lookahead_window) ──
export function adaptCorrelation(d) {
  const basis = str(d?.alignment_basis) ?? 'md'
  const at = values => num(values?.[basis])
  const window = d?.lookahead_window
  return {
    well_id: str(d?.well_id), depth_ref: basis, current_depth_m: at(d?.current_bit_depth), lookahead_m: num(window?.lookahead_m),
    lookahead_window: at(window?.start) != null && at(window?.end) != null ? { top: at(window.start), base: at(window.end) } : null,
    warning: str(d?.warning), as_of: str(d?.as_of), dataset_origin: origin(d),
    tracks: arr(d?.tracks).map(t => {
      const well = adaptWell(t?.well)
      return {
        well_id: well.id, name: well.name, role: t?.is_active ? 'active' : 'offset', td_tvd_m: basis === 'md' ? well.td_md_m : null,
        formations: arr(t?.formations).map(adaptFormation),
        casing: arr(t?.casing_points).map(c => ({ size: num(c?.size_in) == null ? str(c?.source) ?? 'casing' : `${c.size_in}"`, depth: num(c?.[basis]) })),
        events: arr(t?.events).map(adaptEvent).map(e => ({ id: e.id, type: e.type, depth: eventDepth(e, basis), severity: e.severity, confidence: e.confidence,
          verification: e.verification, summary: e.raw_observation, source: e.source })),
      }
    }),
  }
}

// ── RiskAssessment (per hazard; probability ≠ confidence; calibrated=false; the LLM never produces either) ──
function telemetryState(q) {
  if (!q?.telemetry_available) return 'unavailable'
  return q.telemetry_fresh ? 'fresh' : 'stale'
}
function telemetryFeatures(q) {
  const f = q?.telemetry_features
  if (!f || typeof f !== 'object') return []
  return [f.robust_z != null && `Robust deviation z = ${fixed(f.robust_z, 1)} vs. local baseline`,
    f.persistence != null && `Persistence ${f.persistence}/3 latest samples beyond 3σ`,
    f.slope != null && `Slope ${fixed(f.slope, 4)} per second over ${f.count ?? '—'} samples`].filter(Boolean)
}
function confidenceNote(q) {
  if (!q || typeof q !== 'object') return null
  const parts = [q.analog_count != null && `${q.analog_count} analog well${q.analog_count === 1 ? '' : 's'}`,
    q.offset_quality != null && `offset data quality ${fixed(q.offset_quality)}`, q.evidence_quality != null && `evidence quality ${fixed(q.evidence_quality)}`,
    arr(q.depth_bases).length && `depth basis ${arr(q.depth_bases).join('/').toUpperCase()}`,
    `telemetry ${telemetryState(q)}${q.telemetry_mode ? ` (${q.telemetry_mode})` : ''}`,
    q.contradictory_evidence && 'contradictory accounts reduce confidence', q.calibration && `calibration ${q.calibration}`]
  return parts.filter(Boolean).join(' · ')
}
export function normalizeHazard(h) {
  const evidenceIds = ids(pick(h, 'evidence_ids', 'evidence'))
  const quality = h?.data_quality && typeof h.data_quality === 'object' ? h.data_quality : null
  return {
    type: str(pick(h, 'type', 'hazard')), assessmentId: str(h?.assessment_id), probability: num(h?.probability), confidence: num(h?.confidence),
    trend: h?.trend === 'unavailable' ? null : str(h?.trend), severity: str(h?.severity), series: [],
    wells: ids(pick(h, 'supporting_offset_wells', 'supporting_wells')), factors: arr(h?.top_factors).filter(f => typeof f === 'string'),
    evidenceIds, evidenceCount: evidenceIds.length,
    historical: num(pick(h, 'historical_exposure', 'historical_contribution')), telemetry: num(pick(h, 'live_anomaly_contribution', 'telemetry_contribution')),
    telemetryState: telemetryState(quality), telemetryMode: str(quality?.telemetry_mode), telemetryFeatures: telemetryFeatures(quality),
    missing: arr(quality?.missing).filter(m => typeof m === 'string'), confidenceNote: confidenceNote(quality), dataQuality: quality,
  }
}
export function adaptRisk(d) {
  const md = num(d?.current_md_m), lookahead = num(d?.lookahead_m)
  return {
    well_id: str(d?.well_id), as_of: str(d?.as_of), current_md_m: md, current_tvd_m: num(d?.current_tvd_m), formation: str(d?.formation), lookahead_m: lookahead,
    window_md_m: md != null && lookahead != null ? { top: md, base: md + lookahead } : null,
    model_version: str(d?.model_version), calibrated: d?.calibrated === true, advisory_only: d?.advisory_only !== false, dataset_origin: origin(d),
    hazards: arr(d?.hazards).map(normalizeHazard), evidence: [],
  }
}

// ── AssessmentDetail (GET /api/assessments/{id}): assessment → evidence → event → report → page ──
export function adaptAssessment(d) {
  return {
    assessment_id: str(d?.assessment_id), well_id: str(d?.well_id), as_of: str(d?.as_of), current_md_m: num(d?.current_md_m), formation: str(d?.formation),
    lookahead_m: num(d?.lookahead_m), model_version: str(d?.model_version), dataset_origin: origin(d), hazard: d?.hazard ? normalizeHazard(d.hazard) : null,
    evidence: arr(d?.evidence).map(link => {
      const event = adaptEvent(link?.event), atAssessment = link?.event_at_assessment ? adaptEvent(link.event_at_assessment) : null
      return { event, atAssessment, changedSinceAssessment: atAssessment ? JSON.stringify(atAssessment) !== JSON.stringify(event) : null,
        contribution: num(link?.contribution), reason: str(link?.reason), chunkId: str(link?.evidence_chunk_id), sourceUrl: str(link?.source_url),
        sourceHashMatches: link?.source_sha256 != null && link?.source_sha256_at_assessment != null ? link.source_sha256 === link.source_sha256_at_assessment : null }
    }),
  }
}

// ── TelemetrySeries (B2: one row per sample + channels[] states; replay reference time, not the wall clock) ──
const CHANNEL_LABELS = { rop: 'ROP', wob: 'WOB', rpm: 'RPM', md: 'MD', bit_depth: 'Bit depth', torque: 'Torque', hookload: 'Hookload',
  standpipe_pressure: 'Standpipe pressure', flow: 'Flow', mud_weight: 'Mud weight', gas: 'Gas', pit_volume: 'Pit volume' }
const channelLabel = name => CHANNEL_LABELS[String(name).toLowerCase()] ?? String(name).replaceAll('_', ' ')
export function telemetrySeries(d) {
  const byChannel = new Map()
  for (const s of listOf(d)) {
    const channel = str(s?.channel), t = Date.parse(s?.timestamp ?? s?.t)
    if (!channel || !Number.isFinite(t) || num(s?.value) == null || (s?.quality && s.quality !== 'good')) continue
    if (!byChannel.has(channel)) byChannel.set(channel, { unit: str(s?.unit), points: [] })
    byChannel.get(channel).points.push({ t, v: s.value, md: num(s?.md) })
  }
  const states = new Map(arr(d?.channels).map(c => [c?.channel, c]))
  return [...byChannel.entries()].map(([id, { unit, points }]) => ({ id, label: channelLabel(id), unit: unit ?? str(states.get(id)?.unit) ?? '',
    quality: str(states.get(id)?.state), points: points.sort((a, b) => a.t - b.t) }))
}
export function adaptTelemetry(d) {
  const series = telemetrySeries(d)
  const channels = arr(d?.channels).map(c => ({ mnemonic: str(c?.channel), label: channelLabel(c?.channel), unit: str(c?.unit), quality: str(c?.state), known: c?.known === true, valueCount: num(c?.value_count) }))
    .filter(c => c.mnemonic)
  const states = channels.map(c => c.quality)
  const state = !channels.length ? 'unknown' : states.every(s => s === 'unavailable') ? 'unavailable' : states.some(s => s === 'stale') ? 'stale' : states.every(s => s === 'fresh') ? 'fresh' : 'partial'
  const mode = str(d?.source_mode) ?? str(d?.mode)
  return { well_id: str(d?.well_id), mode, source: mode === 'replay' ? 'synthetic replay' : str(d?.source) ?? mode, adapter: str(d?.adapter),
    as_of: str(pick(d, 'freshness_reference', 'as_of')), window_start: str(d?.window_start), window_end: str(d?.window_end), stale_after_s: num(pick(d, 'stale_after_seconds', 'stale_after_s')),
    truncated: d?.has_more === true, dataset_origin: origin(d), state, channels, series,
    missing: channels.filter(c => c.quality === 'unavailable' || !series.some(s => s.id === c.mnemonic)) }
}

// ── KnowledgeEvidence (POST /api/query, mode "nwis_evidence" → answer + evidence[EventOut]) ──
export function adaptQuery(d) {
  const recognized = d?.mode === 'nwis_evidence' && Array.isArray(d?.evidence)
  const events = recognized ? d.evidence.map(adaptEvent) : [] // legacy responses also carry evidence[], in another shape
  const results = events.map(e => ({ kind: 'event', title: `${e.id} · ${e.type ?? 'event'}`, excerpt: e.raw_observation, well_id: e.well_id, event_id: e.id,
    report_id: e.source?.report_id ?? null, page: e.source?.page ?? null, url: e.source?.url ?? null, depth_tvd_m: e.depth_tvd_m, depth_md_m: e.depth_md_m,
    formation: e.formation, confidence: e.confidence, verification: e.verification, mitigation: e.mitigation, dataset_origin: e.dataset_origin }))
  // Wells and reports are the distinct sources of the cited events (grouping only; nothing is added).
  const wells = [...new Set(events.map(e => e.well_id).filter(Boolean))].map(id => ({ kind: 'well', title: id, well_id: id,
    excerpt: `${events.filter(e => e.well_id === id).length} cited event(s)` }))
  const reports = [...new Map(events.filter(e => e.source?.report_id).map(e => [`${e.source.report_id}#${e.source.page}`, e])).values()]
    .map(e => ({ kind: 'report', title: e.source.report_id, report_id: e.source.report_id, page: e.source.page, url: e.source.url, well_id: e.well_id, formation: e.formation, depth_tvd_m: e.depth_tvd_m }))
  return { recognized, status: str(d?.status), answer: str(d?.answer), summary: str(d?.answer), citations: events.map(e => e.id), warnings: arr(d?.warnings).filter(w => typeof w === 'string'),
    mode: str(d?.mode), model_route: str(d?.model_route), results: [...wells, ...results, ...reports], dataset_origin: origin(d) ?? events[0]?.dataset_origin ?? null }
}
export function groupResults(query) {
  const groups = { well: [], event: [], report: [] }
  for (const item of query?.results || []) groups[item.kind in groups ? item.kind : 'report'].push(item)
  return groups
}

// ── Advisory (B2 AdvisoryOut; hazard/evidence come from its assessment) ──
export function adaptAdvisory(a) {
  return {
    id: str(a?.id), assessment_id: str(a?.assessment_id), text: str(pick(a, 'text', 'summary')), status: str(a?.status),
    reviewer: str(a?.reviewer), reviewed_at: str(a?.reviewed_at), reason: str(a?.feedback), model_route: str(a?.model_route),
    created_at: str(a?.created_at), dataset_origin: origin(a),
  }
}
export const adaptAdvisoryList = data => envelope(data, adaptAdvisory)

// ── AuditEvent (GET /api/audit: hash-chained entries; the NWIS action is payload.action) ──
export const adaptAuditEvent = e => {
  const payload = e?.payload && typeof e.payload === 'object' ? e.payload : null
  const { product, action, ...details } = payload || {} // eslint-disable-line no-unused-vars
  return { id: pick(e, 'id'), sequence_number: num(e?.sequence_number), event_type: str(action) ?? str(e?.event_type) ?? 'unknown', raw_type: str(e?.event_type),
    occurred_at: str(e?.occurred_at), actor_id: str(e?.actor_id), actor_kind: str(e?.actor_kind), details: payload ? details : null }
}
export const adaptAuditList = data => envelope(data, adaptAuditEvent)
