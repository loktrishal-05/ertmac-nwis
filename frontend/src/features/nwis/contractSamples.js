// SCHEMA TEST SAMPLES for the NWIS contract — imported by tests only, never by the app, never a fallback.
// Each type has a representative `full` payload and a `sparse` payload exercising nulls / empty lists the backend may send.
// Values are synthetic (dataset_origin = synthetic_demo); they are not Oil India data.
const O = 'synthetic_demo'
const AS_OF = '2026-09-29T16:00:00Z'

export const SAMPLES = {
  well: {
    full: { id: 'ACTIVE-01', name: 'ACTIVE-01', field: 'Demo field', status: 'drilling', role: 'active', lat: 27.4, lon: 95, well_type: 'development', trajectory_type: 'deviated',
      td_md_m: 3250, td_tvd_m: null, data_quality: 0.88, current_md_m: 2450, current_tvd_m: 2382, current_tvdss_m: 2276, current_formation: 'TIPAM_A', hole_section: '12-1/4"',
      formations: [{ name: 'TIPAM_A', top: 2140, base: 2520, confidence: 0.86, interpreted: false }], dataset_origin: O },
    sparse: { id: 'OFF-99', name: null, lat: null, lon: null, status: 'completed', current_tvdss_m: null, data_quality: null, formations: [{ name: 'TIPAM_B', top: null, base: 2890, confidence: null }], dataset_origin: O },
  },
  nearby: {
    full: { radius_km: 5, weights: { geographic: 0.15, formation: 0.25 }, formula: 'Σ wᵢ·componentᵢ', as_of: AS_OF, dataset_origin: O, total: 2, items: [
      { rank: 1, distance_km: 3.1, total_score: 0.89, well: { id: 'OFF-04', lat: 27.39, lon: 95.03, dataset_origin: O },
        components: { geographic: 0.8, formation: 0.95, depth: 0.92, trajectory: 0.85, program: 0.8, data_quality: 0.9 }, event_counts: { stuck_pipe: 1 }, formation_at_depth: 'TIPAM_A', note: null },
      { rank: 2, distance_km: 1.1, total_score: 0.45, well: { id: 'OFF-02', lat: 27.39, lon: 95 },
        components: { geographic: 0.95, formation: 0.22, depth: 0.3, trajectory: 0.45, program: 0.5, data_quality: 0.58 }, event_counts: {}, note: 'Across mapped fault' }] },
    sparse: { items: [], total: 0, radius_km: 2, weights: null, as_of: AS_OF, dataset_origin: O },
  },
  correlation: {
    full: { well_id: 'ACTIVE-01', depth_ref: 'tvd', current_depth_m: 2382, lookahead_m: 100, lookahead_window: { top: 2382, base: 2477 }, as_of: AS_OF, dataset_origin: O,
      tracks: [
        { well_id: 'ACTIVE-01', name: 'ACTIVE-01', role: 'active', td_tvd_m: null, formations: [{ name: 'TIPAM_A', top: 2140, base: 2520, confidence: 0.86 }], casing: [{ size: '13-3/8"', depth: 1100 }], events: [] },
        { well_id: 'OFF-04', role: 'offset', td_tvd_m: 3070, formations: [{ name: 'TIPAM_A', top: 2130, base: 2510, confidence: 0.86 }],
          events: [{ id: 'EVT-102', type: 'stuck_pipe', depth: 2455, severity: 'high', confidence: 0.91, verification: 'verified', summary: 'String stuck after connection.' }] }] },
    sparse: { depth_ref: 'tvd', current_depth_m: null, lookahead_window: null, dataset_origin: O,
      tracks: [{ well_id: 'OFF-03', formations: [{ name: 'TIPAM_B', top: null, base: null, confidence: null, interpreted: true }], events: [{ id: 'EVT-117', type: 'stuck_pipe', depth: null }] }] },
  },
  event: {
    full: { id: 'EVT-102', well_id: 'OFF-04', type: 'stuck_pipe', raw_observation: 'String stuck at 2,529 m MD after connection.', depth_md_m: 2529, depth_tvd_m: 2455, formation: 'TIPAM_A',
      severity: 'high', npt_hours: 14, mitigation: 'Pipe-release pill, jarring.', outcome: 'Freed after 9 h.', confidence: 0.91, verification: 'verified',
      source: { report_id: 'DDR-OFF04-2019-07-13', report_type: 'DDR', page: 2, title: 'Daily Drilling Report' }, dataset_origin: O },
    sparse: { id: 'EVT-900', well_id: 'OFF-03', type: 'mud_loss', raw_observation: null, depth_md_m: null, depth_tvd_m: 2410, formation: null, severity: null,
      npt_hours: null, mitigation: null, outcome: null, confidence: null, verification: 'needs_review', source: { report_id: 'DDR-OFF03', page: null }, dataset_origin: O },
  },
  risk: {
    full: { well_id: 'ACTIVE-01', as_of: AS_OF, current_md_m: 2450, formation: 'TIPAM_A', lookahead_m: 100, window_md_m: { top: 2450, base: 2550 }, model_version: 'hybrid-0.1', dataset_origin: O,
      hazards: [{ type: 'stuck_pipe', probability: 0.72, confidence: 0.78, trend: 'rising', trend_series: [{ md_m: 2440, probability: 0.67 }, { md_m: 2450, probability: 0.72 }],
        supporting_offset_wells: ['OFF-04', 'OFF-09'], top_factors: ['formation_match'], evidence_ids: ['EVT-102'], evidence_count: 1,
        historical_contribution: 0.64, telemetry_contribution: 0.36, data_freshness_s: 20, telemetry_features: ['Torque +21%'], missing_evidence: [], confidence_explanation: 'Two analogs.', advisory_id: 'ADV-0012' }],
      evidence: [] },
    sparse: { as_of: AS_OF, lookahead_m: 150, dataset_origin: O,
      hazards: [{ type: 'kick_or_overpressure', probability: null, confidence: null }] },
  },
  telemetry: {
    full: { well_id: 'ACTIVE-01', mode: 'replay', source: 'synthetic_replay', adapter: 'replay', as_of: AS_OF, stale_after_s: 120, dataset_origin: O,
      channels: [{ mnemonic: 'TORQUE', label: 'Torque', unit: 'kN·m', quality: 'ok' }, { mnemonic: 'PIT', label: 'Pit volume', unit: 'm3', quality: 'missing' }],
      samples: [{ t: '2026-09-29T15:59:00Z', md_m: 2449, values: { TORQUE: 15.2, PIT: null } }, { t: AS_OF, md_m: 2450, values: { TORQUE: 18.9 } }] },
    sparse: { mode: 'replay', as_of: null, dataset_origin: O, channels: [], samples: [] },
  },
  query: {
    full: { mode: 'nwis_evidence', summary: null, citations: [], dataset_origin: O, results: [
      { kind: 'event', title: 'EVT-102 · stuck_pipe', excerpt: 'String stuck…', well_id: 'OFF-04', event_id: 'EVT-102', report_id: 'DDR-OFF04-2019-07-13', page: 2, depth_tvd_m: 2455, formation: 'TIPAM_A', confidence: 0.91, verification: 'verified' },
      { kind: 'report', title: 'Well Completion Report · OFF-04', report_id: 'WCR-OFF04', page: null, well_id: 'OFF-04' }] },
    sparse: { mode: 'nwis_evidence', results: [] },
  },
  advisory: {
    full: { id: 'ADV-0012', well_id: 'ACTIVE-01', hazard: 'stuck_pipe', status: 'open', severity: 'warning', probability: 0.72, confidence: 0.78, lookahead_m: 100,
      interval_md_m: { top: 2450, base: 2550 }, formation: 'TIPAM_A', created_at: AS_OF, evidence_ids: ['EVT-102'], summary: 'Two verified analogs…',
      historical_response: ['OFF-04: pipe-release pill'], model_route: 'template', reviews: [{ reviewer: 'engineer', at: AS_OF, decision: 'acknowledge', feedback: 'useful', note: 'Seen.' }], dataset_origin: O },
    sparse: { id: 'ADV-0099', hazard: 'mud_loss', status: 'open', probability: null, confidence: null, interval_md_m: null, evidence_ids: [], summary: null, reviews: [] },
  },
  audit: {
    full: [{ id: 1, sequence_number: 5007, event_type: 'ALERT_ACKNOWLEDGED', occurred_at: AS_OF, actor_id: 'engineer', actor_kind: 'user', details: { advisory_id: 'ADV-0012', source_path: 'C:\\data\\x.pdf' } }],
    sparse: { items: [{ sequence_number: 1, event_type: 'RISK_ASSESSMENT', occurred_at: null, actor_id: null, details: null }], total: 1 },
  },
}

// Legacy SIH26117 governed-query response shape: must NOT be mistaken for NWIS evidence.
export const LEGACY_QUERY_RESPONSE = { route: 'HYBRID_RAG_PATH', governance_status: 'COMPLETED', agent_result: { output: 'text' }, evidence: [{ evidence_id: 'e1', source_filename: 'sop.pdf' }] }
