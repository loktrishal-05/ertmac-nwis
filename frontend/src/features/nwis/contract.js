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

// B2 schemas (backend app/schemas/nwis.py) — only the fields the adapters read.
const WELL = { id: 'str', name: 'str', field: 'str?', latitude: 'num?', longitude: 'num?', operator: 'str?', status: 'str', spud_date: 'str?',
  total_depth_md: 'num?', current_md: 'num?', as_of: 'str?', dataset_origin: 'str' }
const EVENT = { id: 'str', well_id: 'str', event_type: 'str', start_depth_md: 'num?', end_depth_md: 'num?', tvd: 'num?', tvdss: 'num?', formation: 'str?',
  severity: 'str?', observation: 'str?', cause: 'str?', mitigation: 'str?', outcome: 'str?', npt_hours: 'num?', confidence: 'num?',
  source_report_id: 'str?', source_page: 'num?', raw_phrase: 'str?', verification_state: 'str?', dataset_origin: 'str' }
const MATCH = { offset_well_id: 'str', distance_m: 'num?', distance_km: 'num?', geographic_score: 'num?', formation_score: 'num?', depth_score: 'num?',
  trajectory_score: 'num?', program_score: 'num?', data_quality_score: 'num?', total_score: 'num', depth_basis: 'str?', weights: 'obj?',
  algorithm_version: 'str?', explanation: optionalList('str'), dataset_origin: 'str' }
const DEPTHS = { md: 'num?', tvd: 'num?', tvdss: 'num?' }
const HAZARD = { type: 'str', assessment_id: 'str', probability: 'num?', confidence: 'num', trend: 'str', historical_exposure: 'num?',
  live_anomaly_contribution: 'num?', supporting_offset_wells: ['str'], top_factors: ['str'], evidence_ids: ['str'], data_quality: 'obj' }
const PAGE = { limit: 'num', offset: 'num', has_more: 'bool', as_of: 'str?' }

// Lists are B2 pages: { items, limit, offset, has_more, as_of } (no total).
const list = (item, envelope = PAGE) => ({ list: item, envelope })
export const CONTRACT = {
  wellList: list(WELL),
  well: WELL,
  formationList: list({ formation: 'str', top_md: 'num', bottom_md: 'num', top_tvd: 'num?', bottom_tvd: 'num?', top_tvdss: 'num?', bottom_tvdss: 'num?', confidence: 'num' }),
  nearby: list(MATCH),
  correlation: { well_id: 'str', as_of: 'str', dataset_origin: 'str', alignment_basis: 'str', current_bit_depth: DEPTHS,
    lookahead_window: { lookahead_m: 'num', start: DEPTHS, end: DEPTHS }, warning: 'str?',
    tracks: [{ well: WELL, is_active: 'bool', formations: [{ formation: 'str', top: 'num?', base: 'num?', confidence: 'num?', alignment_available: 'bool?' }],
      events: [EVENT], casing_points: optionalList({ md: 'num', tvd: 'num?', tvdss: 'num?', size_in: 'num?', source: 'str' }) }] },
  eventList: list(EVENT),
  risk: { well_id: 'str', as_of: 'str', current_md_m: 'num?', current_tvd_m: 'num?', formation: 'str?', lookahead_m: 'num', model_version: 'str',
    calibrated: 'bool', advisory_only: 'bool', dataset_origin: 'str', hazards: [HAZARD] },
  assessment: { assessment_id: 'str', well_id: 'str', as_of: 'str', current_md_m: 'num?', formation: 'str?', lookahead_m: 'num', model_version: 'str', dataset_origin: 'str',
    hazard: HAZARD, evidence: [{ event: EVENT, event_at_assessment: { ...EVENT, $optional: true }, contribution: 'num', reason: 'str', source_sha256: 'str',
      source_sha256_at_assessment: 'str?', source_url: 'str' }] },
  telemetry: list({ well_id: 'str', timestamp: 'str', channel: 'str', md: 'num', tvd: 'num?', value: 'num?', unit: 'str', quality: 'str' },
    { ...PAGE, source_mode: 'str', window_start: 'str?', window_end: 'str?', freshness_reference: 'str?', stale_after_seconds: 'num?', dataset_origin: 'str',
      channels: [{ channel: 'str', known: 'bool', unit: 'str?', state: 'str' }] }),
  query: { mode: 'str', status: 'str', answer: 'str', evidence: [EVENT], warnings: ['str'], model_route: 'str', dataset_origin: 'str' },
  advisoryList: list({ id: 'str', assessment_id: 'str', text: 'str', status: 'str', reviewer: 'str?', reviewed_at: 'str?', feedback: 'str?', model_route: 'str',
    created_at: 'str', dataset_origin: 'str' }),
  auditList: list({ id: 'str', sequence_number: 'num', event_type: 'str', occurred_at: 'str', actor_id: 'str?', actor_kind: 'str?', payload: 'obj?' }),
  terms: { version: 'str', text: 'str', accepted: 'bool' },
}

// Returns a list of human-readable problems; [] means the response satisfies what the frontend consumes.
export function validateContract(name, data) {
  const spec = CONTRACT[name]
  if (!spec) throw new Error(`Unknown contract ${name}`)
  const problems = []
  if (spec.list) {
    if (!Array.isArray(data?.items)) return [`${name}: expected { items: [] }`]
    check(data, spec.envelope, name, problems)
    data.items.slice(0, 50).forEach((item, i) => check(item, spec.list, `${name}.items[${i}]`, problems))
    if (name === 'nearby') {
      const scores = data.items.map(item => item?.total_score).filter(T.num)
      if (scores.some((s, i) => i && s > scores[i - 1])) problems.push('nearby: items must be returned in ranking order (total_score descending)')
    }
    return problems
  }
  check(data, spec, name, problems)
  return problems
}
