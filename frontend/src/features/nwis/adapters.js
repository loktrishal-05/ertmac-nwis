// NWIS API → domain adapters: the ONLY place that knows raw backend field names.
// Screens read the canonical shapes returned here (documented in docs/nwis/frontend_api_contract.md).
// If the backend names a field differently, add the alias here, not in a screen.
// Rules: numbers are finite or null (never coerced to 0); strings are non-empty or null; lists are arrays.
import { SCORE_COMPONENTS, listOf, num } from './nwisModel.js'

const str = value => (typeof value === 'string' && value.trim() ? value : null)
const arr = value => (Array.isArray(value) ? value : [])
const pick = (obj, ...keys) => { for (const key of keys) { const value = obj?.[key]; if (value !== undefined && value !== null) return value } return null }
const ids = list => arr(list).map(item => (typeof item === 'string' ? item : str(item?.id) ?? str(item?.well_id) ?? str(item?.event_id))).filter(Boolean)
const interval = value => (value && num(value.top) != null && num(value.base) != null ? { top: value.top, base: value.base } : null)
const origin = (...sources) => sources.map(s => str(s?.dataset_origin)).find(Boolean) ?? null

// Paginated or bare list → { items, total, as_of, dataset_origin, ...extra }.
function envelope(data, adapt, extra = {}) {
  const items = listOf(data).map(adapt)
  return { items, total: num(data?.total) ?? items.length, as_of: str(data?.as_of), dataset_origin: str(data?.dataset_origin), ...extra }
}

// ── Well ──
export function adaptFormation(f) {
  return { name: str(pick(f, 'name', 'formation')), top: num(pick(f, 'top', 'top_tvd_m', 'top_m')), base: num(pick(f, 'base', 'base_tvd_m', 'bottom_tvd_m', 'base_m')),
    confidence: num(f?.confidence), interpreted: f?.interpreted === true }
}
export function adaptWell(w) {
  const id = str(pick(w, 'id', 'well_id'))
  return {
    id, name: str(pick(w, 'name', 'well_name')) ?? id, field: str(w?.field), status: str(w?.status), role: str(w?.role),
    lat: num(pick(w, 'lat', 'latitude')) ?? num(w?.location?.lat) ?? num(w?.location?.coordinates?.[1]),
    lon: num(pick(w, 'lon', 'lng', 'longitude')) ?? num(w?.location?.lon) ?? num(w?.location?.coordinates?.[0]),
    well_type: str(w?.well_type), trajectory_type: str(w?.trajectory_type), trajectory_summary: str(w?.trajectory_summary), spud_date: str(w?.spud_date),
    td_md_m: num(w?.td_md_m), td_tvd_m: num(w?.td_tvd_m), data_quality: num(w?.data_quality),
    current_md_m: num(w?.current_md_m), current_tvd_m: num(w?.current_tvd_m), current_tvdss_m: num(w?.current_tvdss_m),
    current_formation: str(w?.current_formation), hole_section: str(w?.hole_section), note: str(w?.note),
    formations: arr(pick(w, 'formations', 'formation_intervals')).map(adaptFormation),
    upcoming_formations: arr(w?.upcoming_formations).map(f => ({ name: str(pick(f, 'name', 'formation')), top_tvd_m: num(f?.top_tvd_m), distance_m: num(f?.distance_m), confidence: num(f?.confidence) })),
    casing: arr(w?.casing).map(c => ({ size: str(c?.size), shoe_tvd_m: num(pick(c, 'shoe_tvd_m', 'depth')) })),
    dataset_origin: origin(w),
  }
}
export const adaptWellList = data => envelope(data, adaptWell)

// ── NearbyWell (backend order is the ranking) ──
export function normalizeOffset(item) {
  const well = adaptWell(item?.well || item)
  const components = item?.components || item?.component_scores || {}
  return {
    id: well.id ?? str(item?.well_id), name: well.name ?? str(item?.well_id), well,
    distanceKm: num(item?.distance_km), total: num(item?.total_score ?? item?.score), rank: num(item?.rank),
    components: Object.fromEntries(SCORE_COMPONENTS.map(([key]) => [key, num(components[key])])),
    eventCounts: Object.fromEntries(Object.entries(item?.event_counts || {}).filter(([, n]) => num(n) != null)),
    formationAtDepth: str(item?.formation_at_depth), note: str(item?.note) ?? well.note, dataset_origin: origin(item, well),
  }
}
export const rankedOffsets = data => listOf(data).map(normalizeOffset).map((offset, index) => ({ ...offset, rank: offset.rank ?? index + 1 }))
export const adaptNearby = data => ({ items: rankedOffsets(data), total: num(data?.total) ?? listOf(data).length, radius_km: num(data?.radius_km),
  weights: data?.weights && typeof data.weights === 'object' ? data.weights : null, formula: str(data?.formula), as_of: str(data?.as_of), dataset_origin: str(data?.dataset_origin) })

// ── DrillingEvent ──
export function adaptEvent(e) {
  const source = e?.source || {}
  const reportId = str(pick(source, 'report_id', 'document_id')) ?? str(e?.report_id)
  return {
    id: str(pick(e, 'id', 'event_id')), well_id: str(e?.well_id), type: str(pick(e, 'type', 'event_type')),
    raw_observation: str(pick(e, 'raw_observation', 'source_text', 'observation')),
    depth_md_m: num(pick(e, 'depth_md_m', 'md_m')), depth_tvd_m: num(pick(e, 'depth_tvd_m', 'tvd_m')), formation: str(e?.formation),
    severity: str(e?.severity), npt_hours: num(e?.npt_hours), mitigation: str(e?.mitigation), outcome: str(e?.outcome),
    confidence: num(e?.confidence), verification: str(pick(e, 'verification', 'verification_state')),
    source: reportId || num(pick(source, 'page')) != null ? { report_id: reportId, report_type: str(source.report_type), page: num(source.page ?? e?.page), title: str(source.title) } : null,
    dataset_origin: origin(e),
  }
}
export const adaptEventList = data => envelope(data, adaptEvent)

// ── FormationCorrelation ──
export function adaptCorrelation(d) {
  return {
    well_id: str(d?.well_id), depth_ref: str(d?.depth_ref) ?? 'tvd', current_depth_m: num(pick(d, 'current_depth_m', 'current_tvd_m')),
    lookahead_m: num(d?.lookahead_m), lookahead_window: interval(d?.lookahead_window), as_of: str(d?.as_of), dataset_origin: origin(d),
    tracks: arr(d?.tracks).map(t => ({
      well_id: str(pick(t, 'well_id', 'id')), name: str(t?.name) ?? str(pick(t, 'well_id', 'id')), role: str(t?.role), td_tvd_m: num(t?.td_tvd_m),
      formations: arr(t?.formations).map(adaptFormation),
      casing: arr(t?.casing).map(c => ({ size: str(c?.size), depth: num(pick(c, 'depth', 'shoe_tvd_m')) })),
      events: arr(t?.events).map(ev => ({ id: str(pick(ev, 'id', 'event_id')), type: str(pick(ev, 'type', 'event_type')), depth: num(pick(ev, 'depth', 'depth_tvd_m')),
        severity: str(ev?.severity), confidence: num(ev?.confidence), verification: str(ev?.verification), summary: str(pick(ev, 'summary', 'raw_observation')) })),
    })),
  }
}

// ── RiskAssessment (probability and confidence are separate; LLM never supplies either) ──
export function normalizeHazard(h) {
  const evidenceIds = ids(pick(h, 'evidence_ids', 'evidence'))
  return {
    type: str(pick(h, 'type', 'hazard', 'hazard_type')), probability: num(h?.probability), confidence: num(h?.confidence),
    trend: str(h?.trend), severity: str(h?.severity),
    series: arr(h?.trend_series).filter(p => num(p?.probability) != null),
    wells: ids(pick(h, 'supporting_offset_wells', 'supporting_wells')), factors: arr(h?.top_factors).filter(f => typeof f === 'string'),
    evidenceIds, evidenceCount: num(h?.evidence_count) ?? (Array.isArray(pick(h, 'evidence_ids', 'evidence')) ? evidenceIds.length : null),
    historical: num(h?.historical_contribution), telemetry: num(h?.telemetry_contribution), freshnessS: num(h?.data_freshness_s),
    telemetryFeatures: arr(h?.telemetry_features).filter(f => typeof f === 'string'), missing: arr(h?.missing_evidence).filter(f => typeof f === 'string'),
    confidenceNote: str(h?.confidence_explanation), advisoryId: str(h?.advisory_id),
  }
}
export function adaptRisk(d) {
  return {
    well_id: str(d?.well_id), as_of: str(d?.as_of), current_md_m: num(d?.current_md_m), current_tvd_m: num(d?.current_tvd_m), formation: str(d?.formation),
    lookahead_m: num(d?.lookahead_m), window_md_m: interval(d?.window_md_m), model_version: str(d?.model_version), dataset_origin: origin(d),
    hazards: arr(d?.hazards).map(normalizeHazard), evidence: arr(d?.evidence).map(adaptEvent),
  }
}

// ── TelemetrySeries: one series per declared channel that actually has values; never fabricate channels ──
export function telemetrySeries(d) {
  const samples = arr(pick(d, 'samples', 'data'))
  return arr(d?.channels).map(channel => ({
    id: channel?.mnemonic, label: str(channel?.label) ?? channel?.mnemonic, unit: str(channel?.unit) ?? '', quality: str(channel?.quality),
    points: samples.map(s => ({ t: Date.parse(s?.t ?? s?.time ?? s?.timestamp), v: s?.values?.[channel?.mnemonic] ?? s?.[channel?.mnemonic], md: num(pick(s, 'md_m', 'md')) }))
      .filter(p => Number.isFinite(p.t) && num(p.v) != null),
  })).filter(series => series.id && series.points.length)
}
export function adaptTelemetry(d) {
  const series = telemetrySeries(d)
  const channels = arr(d?.channels).map(c => ({ mnemonic: str(c?.mnemonic), label: str(c?.label), unit: str(c?.unit), quality: str(c?.quality) })).filter(c => c.mnemonic)
  return { well_id: str(d?.well_id), mode: str(d?.mode), source: str(d?.source), adapter: str(d?.adapter), as_of: str(d?.as_of), stale_after_s: num(d?.stale_after_s),
    dataset_origin: origin(d), channels, series, missing: channels.filter(c => !series.some(s => s.id === c.mnemonic)) }
}

// ── KnowledgeEvidence (POST /query, mode nwis_evidence). A legacy governed-query response is reported as unrecognised. ──
export function adaptQuery(d) {
  const recognized = Array.isArray(d?.results)
  const results = arr(d?.results).map(r => ({
    kind: ['well', 'event', 'report'].includes(r?.kind) ? r.kind : 'report', title: str(r?.title), excerpt: str(pick(r, 'excerpt', 'text', 'snippet')),
    well_id: str(r?.well_id), event_id: str(r?.event_id), report_id: str(r?.report_id) ?? str(r?.source?.report_id), page: num(r?.page) ?? num(r?.source?.page),
    depth_tvd_m: num(r?.depth_tvd_m), depth_md_m: num(r?.depth_md_m), formation: str(r?.formation), confidence: num(r?.confidence),
    verification: str(r?.verification), mitigation: str(r?.mitigation), dataset_origin: origin(r),
  }))
  return { recognized, results, summary: str(d?.summary), citations: arr(d?.citations), mode: str(d?.mode), dataset_origin: origin(d) }
}
export function groupResults(query) {
  const groups = { well: [], event: [], report: [] }
  for (const item of query?.results || []) groups[item.kind].push(item)
  return groups
}

// ── Advisory ──
export function adaptAdvisory(a) {
  return {
    id: str(pick(a, 'id', 'advisory_id')), well_id: str(a?.well_id), hazard: str(pick(a, 'hazard', 'hazard_type', 'type')), status: str(a?.status),
    severity: str(a?.severity), probability: num(a?.probability), confidence: num(a?.confidence), lookahead_m: num(a?.lookahead_m),
    interval_md_m: interval(a?.interval_md_m), formation: str(a?.formation), created_at: str(a?.created_at), evidence_ids: ids(a?.evidence_ids),
    summary: str(pick(a, 'summary', 'advisory_text')), historical_response: arr(a?.historical_response).filter(r => typeof r === 'string'), model_route: str(a?.model_route),
    reviews: arr(a?.reviews).map(r => ({ reviewer: str(pick(r, 'reviewer', 'reviewer_id', 'actor')), at: str(pick(r, 'at', 'reviewed_at', 'created_at')),
      decision: str(r?.decision), feedback: str(r?.feedback), note: str(r?.note) })),
    dataset_origin: origin(a),
  }
}
export const adaptAdvisoryList = data => envelope(data, adaptAdvisory)

// ── AuditEvent (existing tamper-evident chain) ──
export const adaptAuditEvent = e => ({ id: pick(e, 'id', 'event_id'), sequence_number: num(e?.sequence_number), event_type: str(e?.event_type) ?? 'unknown',
  occurred_at: str(e?.occurred_at), actor_id: str(e?.actor_id), actor_kind: str(e?.actor_kind), details: e?.details ?? e?.payload ?? null })
export const adaptAuditList = data => envelope(data, adaptAuditEvent)
