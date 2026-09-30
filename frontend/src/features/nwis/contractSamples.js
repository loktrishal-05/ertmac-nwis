// SCHEMA TEST SAMPLES for the NWIS B2 contract — imported by tests only, never by the app, never a fallback.
// `full` payloads are trimmed from real B2 responses (synthetic_demo seed); `sparse` payloads exercise the nulls and empty lists B2 may send.
// Values are synthetic (dataset_origin = synthetic_demo); they are not Oil India data.
const O = 'synthetic_demo'
const AS_OF = '2026-09-29T16:00:00Z'
const PAGE = { limit: 100, offset: 0, has_more: false, as_of: AS_OF }

const WELL = { id: 'ACTIVE-01', name: 'ACTIVE-01', field: 'SYNTHETIC-ASSAM-DEMO', latitude: 27.4, longitude: 95.3, operator: 'Synthetic demo operator', status: 'ACTIVE',
  spud_date: '2025-01-01', total_depth_md: 3200, current_md: 2450, as_of: AS_OF, dataset_origin: O }
const OFF04 = { ...WELL, id: 'OFF-04', name: 'OFF-04', latitude: 27.412, longitude: 95.308, status: 'historical', current_md: null }
const EVENT = { id: 'EVT-d425ce494054e5fa', well_id: 'OFF-04', event_type: 'stuck_pipe', start_depth_md: 2410, end_depth_md: 2415, tvd: 2410, tvdss: null, formation: 'TIPAM_A',
  severity: 'warning', observation: 'Historical synthetic stuck_pipe reported', cause: null, mitigation: 'Engineering review and documented site procedure used',
  outcome: 'Synthetic incident resolved', npt_hours: 2, confidence: 0.9, source_report_id: 'OFF-04-DDR', source_page: 1, source_span: null,
  raw_phrase: 'Well: OFF-04; Event: stuck_pipe; Formation: TIPAM_A; MD: 2410.00-2415.00 m', verification_state: 'unverified', dataset_origin: O }
const SPARSE_EVENT = { id: 'EVT-900', well_id: 'OFF-03', event_type: 'mud_loss', start_depth_md: null, end_depth_md: null, tvd: 2410, tvdss: null, formation: null, severity: null,
  observation: null, cause: null, mitigation: null, outcome: null, npt_hours: null, confidence: null, source_report_id: 'OFF-03-DDR', source_page: null, source_span: null,
  raw_phrase: null, verification_state: 'review_needed', dataset_origin: O }
const HAZARD = { type: 'stuck_pipe', assessment_id: 'a1b2c3', probability: 0.7455, confidence: 0.855, trend: 'rising', historical_exposure: 0.7, live_anomaly_contribution: 0.15,
  supporting_offset_wells: ['OFF-04', 'OFF-09'], top_factors: ['formation_match', 'historical_event_prevalence', 'live_anomaly'], evidence_ids: [EVENT.id],
  data_quality: { analog_count: 10, offset_quality: 0.95, evidence_quality: 0.9, telemetry_available: true, telemetry_fresh: true,
    telemetry_features: { robust_z: 3.4, persistence: 3, slope: 0.0021, count: 31 }, telemetry_mode: 'replay', depth_bases: ['tvd'], contradictory_evidence: false,
    calibration: 'unavailable', missing: [] } }
const SPARSE_HAZARD = { type: 'kick_or_overpressure', assessment_id: 'd4e5f6', probability: null, confidence: 0.2, trend: 'unavailable', historical_exposure: null,
  live_anomaly_contribution: null, supporting_offset_wells: [], top_factors: [], evidence_ids: [],
  data_quality: { analog_count: 0, telemetry_available: false, telemetry_fresh: false, calibration: 'unavailable', missing: ['analog_offsets'] } }

export const SAMPLES = {
  well: { full: WELL, sparse: { id: 'OFF-99', name: 'OFF-99', field: null, latitude: null, longitude: null, operator: null, status: 'historical', spud_date: null,
    total_depth_md: null, current_md: null, as_of: null, dataset_origin: O } },
  nearby: {
    full: { ...PAGE, items: [
      { offset_well_id: 'OFF-04', distance_m: 1547.3, distance_km: 1.5473, geographic_score: 0.734, formation_score: 1, depth_score: 1, trajectory_score: 1, program_score: 1,
        data_quality_score: 0.95, total_score: 0.955, depth_basis: 'tvd', weights: { geographic: 0.15, formation: 0.3, depth: 0.2, trajectory: 0.15, program: 0.1, data_quality: 0.1 },
        algorithm_version: 'nwis-hybrid-v2', dataset_origin: O, explanation: ['1.5 km from the active well (geographic 0.73)', 'penetrated the active formation TIPAM_A'] },
      { offset_well_id: 'OFF-02', distance_m: 773.6, distance_km: 0.7736, geographic_score: 0.857, formation_score: 1, depth_score: 1, trajectory_score: 0.744, program_score: null,
        data_quality_score: 0.95, total_score: 0.935, depth_basis: 'tvd', weights: null, algorithm_version: 'nwis-hybrid-v2', dataset_origin: O, explanation: [] }] },
    sparse: { ...PAGE, items: [] },
  },
  correlation: {
    full: { well_id: 'ACTIVE-01', as_of: AS_OF, dataset_origin: O, alignment_basis: 'tvd', current_bit_depth: { md: 2450, tvd: 2450, tvdss: null },
      lookahead_window: { lookahead_m: 100, start: { md: 2450, tvd: 2450, tvdss: null }, end: { md: 2550, tvd: 2550, tvdss: null } },
      warning: 'Formation analogs do not establish geological continuity. Missing datums remain unavailable.',
      tracks: [
        { well: WELL, is_active: true, formations: [{ interval_id: 'ACTIVE-01-F2', formation: 'TIPAM_A', top: 2300, base: 2800, confidence: 0.95, source: 'synthetic formation table', alignment_available: true }],
          events: [], casing_points: null },
        { well: OFF04, is_active: false, formations: [{ interval_id: 'OFF-04-F2', formation: 'TIPAM_A', top: 2300, base: 2800, confidence: 0.95, source: 'synthetic formation table', alignment_available: true }],
          events: [EVENT], casing_points: [{ md: 1100, tvd: 1100, tvdss: null, size_in: 13.375, source: 'WCR' }] }] },
    sparse: { well_id: 'ACTIVE-01', as_of: AS_OF, dataset_origin: O, alignment_basis: 'md', current_bit_depth: { md: null, tvd: null, tvdss: null },
      lookahead_window: { lookahead_m: 100, start: { md: null, tvd: null, tvdss: null }, end: { md: null, tvd: null, tvdss: null } }, warning: null,
      tracks: [{ well: { ...OFF04, id: 'OFF-03', name: 'OFF-03' }, is_active: false,
        formations: [{ interval_id: 'OFF-03-F3', formation: 'TIPAM_B', top: null, base: null, confidence: null, alignment_available: false }], events: [SPARSE_EVENT], casing_points: null }] },
  },
  event: { full: EVENT, sparse: SPARSE_EVENT },
  risk: {
    full: { well_id: 'ACTIVE-01', as_of: AS_OF, current_md_m: 2450, current_tvd_m: 2450, formation: 'TIPAM_A', lookahead_m: 100, model_version: 'nwis-hybrid-v2',
      calibrated: false, advisory_only: true, dataset_origin: O, hazards: [HAZARD] },
    sparse: { well_id: 'ACTIVE-01', as_of: AS_OF, current_md_m: null, current_tvd_m: null, formation: null, lookahead_m: 150, model_version: 'nwis-hybrid-v2',
      calibrated: false, advisory_only: true, dataset_origin: O, hazards: [SPARSE_HAZARD] },
  },
  assessment: {
    full: { assessment_id: HAZARD.assessment_id, well_id: 'ACTIVE-01', as_of: AS_OF, current_md_m: 2450, formation: 'TIPAM_A', lookahead_m: 100, model_version: 'nwis-hybrid-v2',
      dataset_origin: O, hazard: HAZARD, evidence: [{ event: EVENT, event_at_assessment: EVENT, evidence_chunk_id: null, contribution: 0.12, reason: 'offset analog at equivalent TVD',
        source_sha256: 'abc', source_sha256_at_assessment: 'abc', source_url: '/api/reports/OFF-04-DDR/source#page=1' }] },
    sparse: { assessment_id: 'd4e5f6', well_id: 'ACTIVE-01', as_of: AS_OF, current_md_m: null, formation: null, lookahead_m: 150, model_version: 'nwis-hybrid-v2',
      dataset_origin: O, hazard: SPARSE_HAZARD, evidence: [] },
  },
  telemetry: {
    full: { ...PAGE, as_of: AS_OF, dataset_origin: O, source_mode: 'replay', window_start: '2026-09-29T15:00:00Z', window_end: AS_OF, freshness_reference: AS_OF, stale_after_seconds: 300,
      items: [
        { well_id: 'ACTIVE-01', timestamp: '2026-09-29T15:59:00Z', channel: 'torque', md: 2449, tvd: 2449, value: 15.2, unit: 'kN.m', quality: 'good', dataset_origin: O },
        { well_id: 'ACTIVE-01', timestamp: AS_OF, channel: 'torque', md: 2450, tvd: 2450, value: 18.9, unit: 'kN.m', quality: 'good', dataset_origin: O },
        { well_id: 'ACTIVE-01', timestamp: AS_OF, channel: 'pit_volume', md: 2450, tvd: 2450, value: null, unit: 'm3', quality: 'missing', dataset_origin: O }],
      channels: [{ channel: 'torque', known: true, unit: 'kN.m', sample_count: 2, value_count: 2, state: 'fresh' },
        { channel: 'pit_volume', known: true, unit: 'm3', sample_count: 1, value_count: 0, state: 'unavailable' }] },
    sparse: { ...PAGE, as_of: null, dataset_origin: O, source_mode: 'replay', window_start: null, window_end: null, freshness_reference: null, stale_after_seconds: 300, items: [], channels: [] },
  },
  query: {
    full: { mode: 'nwis_evidence', execution_id: '00000000-0000-4000-8000-000000000001', status: 'completed', answer: 'Two cited stuck-pipe events in TIPAM_A.',
      evidence: [EVENT, { ...EVENT, id: 'EVT-2', source_page: null }], offsets: [], risk: null, warnings: [], model_route: 'deterministic', as_of: AS_OF, dataset_origin: O },
    sparse: { mode: 'nwis_evidence', execution_id: '00000000-0000-4000-8000-000000000002', status: 'refused', answer: 'NWIS answers drilling-evidence questions only.',
      evidence: [], offsets: [], risk: null, warnings: ['out_of_scope'], model_route: 'deterministic', as_of: AS_OF, dataset_origin: O },
  },
  advisory: {
    full: { id: 'ADV-1', assessment_id: HAZARD.assessment_id, text: 'Sustained stuck-pipe exposure in the next 100 m; cited analogs OFF-04, OFF-09.', status: 'acknowledged',
      reviewer: '5f0c1d7e-0000-4000-8000-000000000000', reviewed_at: AS_OF, feedback: 'Seen; hole cleaning checked.', model_route: 'template', dataset_origin: O, created_at: AS_OF },
    sparse: { id: 'ADV-2', assessment_id: 'd4e5f6', text: 'Advisory text.', status: 'pending_review', reviewer: null, reviewed_at: null, feedback: null, model_route: 'template',
      dataset_origin: O, created_at: AS_OF },
  },
  audit: {
    full: { ...PAGE, items: [{ id: '882fd695', chain_id: 'workbench-governance-v1', sequence_number: 7, occurred_at: AS_OF, actor_id: 'bc9b07bc', actor_kind: 'user',
      event_type: 'PRODUCT_INTEGRATION_EVENT', payload: { action: 'advisory_review', product: 'SIH26121', advisory_id: 'ADV-1', status: 'acknowledged', source_path: 'C:\\data\\x.pdf' } }] },
    sparse: { ...PAGE, items: [{ id: 'x', sequence_number: 1, occurred_at: AS_OF, actor_id: null, actor_kind: null, event_type: 'PRODUCT_INTEGRATION_EVENT', payload: null }] },
  },
}

// Legacy SIH26117 governed-query response shape: must NOT be mistaken for NWIS evidence.
export const LEGACY_QUERY_RESPONSE = { route: 'HYBRID_RAG_PATH', governance_status: 'COMPLETED', agent_result: { output: 'text' }, evidence: [{ evidence_id: 'e1', source_filename: 'sop.pdf' }] }
