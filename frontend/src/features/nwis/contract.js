// Executable form of docs/nwis/frontend_api_contract.md: what the frontend REQUIRES from each NWIS response.
// Rule strings: 'str' | 'num' | 'bool' | 'obj' | 'any', suffix '?' = nullable/optional. Arrays: [itemRule]. Objects: { key: rule, $optional? }.
// Used by unit tests (fixtures + schema samples) and by scripts/nwis-contract-check.mjs against a running backend.

const T = { str: v => typeof v === 'string', num: v => typeof v === 'number' && Number.isFinite(v), bool: v => typeof v === 'boolean', obj: v => !!v && typeof v === 'object' && !Array.isArray(v), any: () => true }

function check(value, rule, where, problems) {
  if (typeof rule === 'string') {
    const optional = rule.endsWith('?'), type = rule.replace('?', '')
    if (value == null) { if (!optional) problems.push(`${where}: required ${type} is missing`); return }
    if (!T[type](value)) problems.push(`${where}: expected ${type}, got ${Array.isArray(value) ? 'array' : typeof value}`)
    return
  }
  if (Array.isArray(rule)) {
    if (value == null && rule.optional) return
    if (!Array.isArray(value)) { problems.push(`${where}: expected array`); return }
    value.slice(0, 50).forEach((item, i) => check(item, rule[0], `${where}[${i}]`, problems))
    return
  }
  if (value == null && rule.$optional) return
  if (!T.obj(value)) { problems.push(`${where}: expected object`); return }
  for (const [key, sub] of Object.entries(rule)) if (key !== '$optional') check(value[key], sub, `${where}.${key}`, problems)
}
const optionalList = item => Object.assign([item], { optional: true })

const FORMATION = { name: 'str', top: 'num?', base: 'num?', confidence: 'num?', interpreted: 'bool?' }
const SOURCE = { $optional: true, report_id: 'str?', page: 'num?', title: 'str?' }
const WELL = { id: 'str', name: 'str?', field: 'str?', status: 'str?', role: 'str?', lat: 'num?', lon: 'num?', well_type: 'str?', trajectory_type: 'str?',
  td_md_m: 'num?', td_tvd_m: 'num?', data_quality: 'num?', current_md_m: 'num?', current_tvd_m: 'num?', current_tvdss_m: 'num?',
  current_formation: 'str?', hole_section: 'str?', formations: optionalList(FORMATION), dataset_origin: 'str?' }
const EVENT = { id: 'str', well_id: 'str', type: 'str', raw_observation: 'str?', depth_md_m: 'num?', depth_tvd_m: 'num?', formation: 'str?', severity: 'str?',
  npt_hours: 'num?', mitigation: 'str?', outcome: 'str?', confidence: 'num?', verification: 'str?', source: SOURCE, dataset_origin: 'str?' }
const HAZARD = { type: 'str', probability: 'num?', confidence: 'num?', trend: 'str?', severity: 'str?', trend_series: optionalList({ probability: 'num?' }),
  supporting_offset_wells: optionalList('str'), top_factors: optionalList('str'), evidence_ids: optionalList('str'), evidence_count: 'num?',
  historical_contribution: 'num?', telemetry_contribution: 'num?', data_freshness_s: 'num?', telemetry_features: optionalList('str'),
  missing_evidence: optionalList('str'), confidence_explanation: 'str?', advisory_id: 'str?' }
const ADVISORY = { id: 'str', well_id: 'str?', hazard: 'str', status: 'str', severity: 'str?', probability: 'num?', confidence: 'num?',
  interval_md_m: { $optional: true, top: 'num', base: 'num' }, evidence_ids: optionalList('str'), summary: 'str?', historical_response: optionalList('str'),
  reviews: optionalList({ reviewer: 'str?', at: 'str?', decision: 'str', note: 'str?' }), dataset_origin: 'str?' }
const AUDIT = { sequence_number: 'num', event_type: 'str', occurred_at: 'str?', actor_id: 'str?', actor_kind: 'str?', details: 'obj?' }

// Lists may be a bare array or { items, total }.
const list = item => ({ list: item })
export const CONTRACT = {
  wellList: list(WELL),
  well: WELL,
  nearby: { envelope: { radius_km: 'num?', weights: 'obj?', formula: 'str?', as_of: 'str?', dataset_origin: 'str?' },
    list: { well: WELL, distance_km: 'num?', total_score: 'num?', rank: 'num?', components: { geographic: 'num?', formation: 'num?', depth: 'num?', trajectory: 'num?', program: 'num?', data_quality: 'num?' },
      event_counts: 'obj?', formation_at_depth: 'str?', note: 'str?' } },
  correlation: { well_id: 'str?', depth_ref: 'str', current_depth_m: 'num?', lookahead_m: 'num?', lookahead_window: { $optional: true, top: 'num', base: 'num' }, as_of: 'str?', dataset_origin: 'str?',
    tracks: [{ well_id: 'str', name: 'str?', role: 'str?', td_tvd_m: 'num?', formations: [FORMATION], casing: optionalList({ size: 'str?', depth: 'num?' }),
      events: [{ id: 'str', type: 'str', depth: 'num?', severity: 'str?', confidence: 'num?', verification: 'str?', summary: 'str?' }] }] },
  eventList: list(EVENT),
  risk: { well_id: 'str?', as_of: 'str', current_md_m: 'num?', formation: 'str?', lookahead_m: 'num', window_md_m: { $optional: true, top: 'num', base: 'num' },
    model_version: 'str?', dataset_origin: 'str?', hazards: [HAZARD], evidence: optionalList(EVENT) },
  telemetry: { well_id: 'str?', mode: 'str', source: 'str?', adapter: 'str?', as_of: 'str?', stale_after_s: 'num?', dataset_origin: 'str?',
    channels: [{ mnemonic: 'str', label: 'str?', unit: 'str?', quality: 'str?' }], samples: [{ t: 'str', md_m: 'num?', values: 'obj' }] },
  query: { mode: 'str?', summary: 'str?', citations: optionalList('any'), dataset_origin: 'str?',
    results: [{ kind: 'str', title: 'str?', excerpt: 'str?', well_id: 'str?', event_id: 'str?', report_id: 'str?', page: 'num?', depth_tvd_m: 'num?', depth_md_m: 'num?',
      formation: 'str?', confidence: 'num?', verification: 'str?' }] },
  advisoryList: list(ADVISORY),
  advisory: ADVISORY,
  auditList: list(AUDIT),
}

// Returns a list of human-readable problems; [] means the response satisfies what the frontend consumes.
export function validateContract(name, data) {
  const spec = CONTRACT[name]
  if (!spec) throw new Error(`Unknown contract ${name}`)
  const problems = []
  if (spec.list) {
    const items = Array.isArray(data) ? data : data?.items
    if (!Array.isArray(items)) return [`${name}: expected an array or { items: [] }`]
    if (!Array.isArray(data) && data.total != null && !T.num(data.total)) problems.push(`${name}.total: expected num`)
    if (spec.envelope && !Array.isArray(data)) check(data, spec.envelope, name, problems)
    items.slice(0, 50).forEach((item, i) => check(item, spec.list, `${name}.items[${i}]`, problems))
    if (name === 'nearby') {
      const ranks = items.map(item => item?.rank).filter(T.num)
      if (ranks.some((r, i) => i && r < ranks[i - 1])) problems.push('nearby: items must be returned in rank order (backend order is the ranking)')
    }
    return problems
  }
  check(data, spec, name, problems)
  if (name === 'query') for (const [i, r] of (data?.results || []).entries()) if (!['well', 'event', 'report'].includes(r?.kind)) problems.push(`query.results[${i}].kind: expected well | event | report`)
  return problems
}
