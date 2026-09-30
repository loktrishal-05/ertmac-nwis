// DEVELOPMENT FIXTURE LAYER — synthetic_demo data only. Documented in docs/nwis/frontend_fixtures.md.
// Loaded only when `import.meta.env.DEV` AND `VITE_NWIS_FIXTURES=1` (see services/api.js); a production build
// never contains this module. Nothing here is Oil India data; every record carries dataset_origin="synthetic_demo".
// It mirrors the B2 response shapes (docs/nwis/frontend_api_contract.md) so screens can be exercised without the backend.

const ORIGIN = 'synthetic_demo'
const FIELD = 'NWIS Demo Field (synthetic)'
const CENTER = [27.4, 95.0] // lat, lon of ACTIVE-01; arbitrary synthetic position
const WEIGHTS = { geographic: 0.15, formation: 0.25, depth: 0.25, trajectory: 0.12, program: 0.08, data_quality: 0.15 }
const KEYS = Object.keys(WEIGHTS)
const MD_FACTOR = { vertical: 1, deviated: 1.03, 'J-shape': 1.03, 'S-shape': 1.02, horizontal: 1.08 }

// Base stratigraphy for ACTIVE-01 (TVD m). Offsets shift it structurally.
const STRAT = [['NAMSANG', 380, 1120], ['GIRUJAN', 1120, 2140], ['TIPAM_A', 2140, 2520], ['TIPAM_B', 2520, 2890], ['BARAIL', 2890, 3400]]

// id, distance km, bearing°, status, type, trajectory, spud year, TD TVD, structural shift m, component scores [geo, formation, depth, trajectory, program, dq], note
const OFFSETS = [
  ['OFF-01', 6.8, 40, 'completed', 'development', 'deviated', 2016, 3150, 15, [0.55, 0.85, 0.8, 0.7, 0.65, 0.82]],
  ['OFF-02', 1.1, 200, 'completed', 'development', 'vertical', 2011, 2980, -600, [0.95, 0.22, 0.3, 0.45, 0.5, 0.58], 'Across mapped fault F-2: Tipam A penetrated ~600 m shallower, so the equivalent TVD is in Barail.'],
  ['OFF-03', 2.9, 310, 'completed', 'exploratory', 'vertical', 2008, 2900, 30, [0.82, 0.7, 0.62, 0.45, 0.4, 0.45], 'Scanned 2008 DDRs; several depth values have low OCR confidence.'],
  ['OFF-04', 3.1, 95, 'completed', 'development', 'J-shape', 2019, 3080, -10, [0.8, 0.95, 0.92, 0.85, 0.8, 0.9]],
  ['OFF-05', 8.9, 150, 'completed', 'development', 'vertical', 2014, 2950, 40, [0.42, 0.8, 0.75, 0.5, 0.6, 0.7]],
  ['OFF-06', 12.5, 250, 'abandoned', 'exploratory', 'vertical', 2004, 3300, 90, [0.28, 0.6, 0.4, 0.45, 0.3, 0.35]],
  ['OFF-07', 5.6, 60, 'completed', 'development', 'deviated', 2020, 3120, 5, [0.62, 0.88, 0.84, 0.8, 0.75, 0.86]],
  ['OFF-08', 17.8, 20, 'completed', 'development', 'horizontal', 2021, 2600, 60, [0.15, 0.65, 0.55, 0.3, 0.6, 0.88]],
  ['OFF-09', 4.4, 130, 'completed', 'development', 'deviated', 2018, 3050, 0, [0.7, 0.92, 0.9, 0.82, 0.78, 0.84]],
  ['OFF-10', 9.7, 330, 'suspended', 'development', 'S-shape', 2012, 2980, 25, [0.38, 0.72, 0.66, 0.6, 0.5, 0.52]],
  ['OFF-11', 14.2, 190, 'completed', 'exploratory', 'vertical', 2009, 3200, 110, [0.22, 0.5, 0.45, 0.4, 0.35, 0.4]],
  ['OFF-12', 1.9, 20, 'completed', 'development', 'vertical', 2023, 1850, 10, [0.9, 0.35, 0.1, 0.5, 0.55, 0.76], 'TD 1,850 m TVD: never reached the active interval.'],
  ['OFF-13', 19.4, 280, 'completed', 'development', 'deviated', 2015, 3000, 70, [0.12, 0.7, 0.6, 0.7, 0.55, 0.6]],
]

function place(distanceKm, bearingDeg) {
  const b = (bearingDeg * Math.PI) / 180
  return [+(CENTER[0] + (distanceKm * Math.cos(b)) / 111.32).toFixed(5), +(CENTER[1] + (distanceKm * Math.sin(b)) / (111.32 * Math.cos((CENTER[0] * Math.PI) / 180))).toFixed(5)]
}
const formationsFor = (shift, tdTvd, id) => STRAT.map(([name, top, base]) => ({ name, top: top + shift, base: Math.min(base + shift, tdTvd) }))
  .filter(f => f.top < tdTvd)
  .map(f => ({ ...f, confidence: id === 'OFF-03' && f.name === 'TIPAM_B' ? null : f.name === 'BARAIL' ? 0.62 : 0.86, interpreted: f.name === 'BARAIL' || (id === 'OFF-03' && f.name === 'TIPAM_B') }))

const AS_OF = '2026-09-29T16:00:00Z' // replay reference time, as in the B2 demo seed
const at = minutes => new Date(Date.parse(AS_OF) - minutes * 60000).toISOString()
const page = (items, limit = 50) => ({ items: items.slice(0, limit), limit, offset: 0, has_more: items.length > limit, as_of: AS_OF })
const round = (value, digits = 3) => +value.toFixed(digits)
const SIZE_IN = { '13-3/8"': 13.375, '9-5/8"': 9.625 }

const ACTIVE = { id: 'ACTIVE-01', lat: CENTER[0], lon: CENTER[1], role: 'active', trajectory_type: 'deviated', spud_date: '2026-08-21', td_md_m: 3250,
  current_md_m: 2450, current_tvd_m: 2382, current_formation: 'TIPAM_A', formations: formationsFor(0, 3400, 'ACTIVE-01'), casing: [['13-3/8"', 1100]] }

const WELLS = [ACTIVE, ...OFFSETS.map(([id, distance, bearing, , , trajectory, year, td, shift, scores, note]) => {
  const [lat, lon] = place(distance, bearing)
  return { id, lat, lon, role: 'offset', trajectory_type: trajectory, spud_date: `${year}-01-15`, td_md_m: Math.round(td * MD_FACTOR[trajectory]),
    formations: formationsFor(shift, td, id), casing: [['13-3/8"', 1100 + shift], ['9-5/8"', Math.min(td, 2500 + shift)]],
    distance, scores: Object.fromEntries(KEYS.map((key, i) => [key, scores[i]])), note: note || null }
})]
const wellById = id => WELLS.find(w => w.id === id)
const formationAt = (well, tvd) => well.formations.find(f => tvd >= f.top && tvd < f.base)?.name || null
const mdAt = (well, tvd) => Math.round(tvd * MD_FACTOR[well.trajectory_type])
const wellOut = w => ({ id: w.id, name: w.id, field: FIELD, latitude: w.lat, longitude: w.lon, operator: 'Synthetic demo operator', status: w.role === 'active' ? 'ACTIVE' : 'historical',
  spud_date: w.spud_date, total_depth_md: w.td_md_m, current_md: w.role === 'active' ? w.current_md_m : null, as_of: AS_OF, dataset_origin: ORIGIN })
const formationOut = well => (f, i) => ({ id: `${well.id}-F${i}`, well_id: well.id, formation: f.name, top_md: mdAt(well, f.top), bottom_md: mdAt(well, f.base),
  top_tvd: f.top, bottom_tvd: f.base, top_tvdss: null, bottom_tvdss: null, confidence: f.confidence ?? 0.4, source: 'fixture formation table', dataset_origin: ORIGIN })

// well, type, TVD m, severity, NPT h, source wording, mitigation, outcome, report, page, confidence, verification
const EVENT_ROWS = [
  ['OFF-04', 'torque_drag', 2428, 'moderate', 0, 'Torque erratic 18-24 kN.m while drilling 12-1/4" hole at 2,501 m MD; overpull 25 t on connection.', 'Reduced WOB to 12 t, increased flow to 3,400 L/min, back-reamed one stand.', 'Torque stabilised after two stands.', 'DDR-OFF04-2019-07-12', 3, 0.86, 'verified'],
  ['OFF-04', 'stuck_pipe', 2455, 'high', 14, 'String stuck at 2,529 m MD after connection; unable to rotate, circulation established. Suspected differential sticking across Tipam sand.', 'Spotted pipe-release pill, worked string with jar at 80 t overpull.', 'Freed after 9 h; 14 h NPT including conditioning trip.', 'DDR-OFF04-2019-07-13', 2, 0.91, 'verified'],
  ['OFF-04', 'mud_loss', 2510, 'moderate', 3, 'Partial losses 6-8 m3/h at 2,585 m MD.', 'LCM pill 40 kg/m3 medium calcium carbonate; ECD reduced by 0.03 sg.', 'Losses cured after second pill.', 'WCR-OFF04', 14, 0.82, 'verified'],
  ['OFF-04', 'cementing_issue', 2560, 'low', 2, 'Partial returns during 9-5/8" primary cement job.', 'Top-up job through annulus.', 'CBL acceptable above 2,300 m MD.', 'WCR-OFF04', 21, 0.74, 'needs_review'],
  ['OFF-09', 'torque_drag', 2440, 'moderate', 0, 'Torque rising ~20% over 30 m while drilling ahead in Tipam sand; drag trend up on connections.', 'Increased RPM to 140 and circulated bottoms-up before each connection.', 'Trend flattened; drilled ahead.', 'DDR-OFF09-2018-03-01', 3, 0.8, 'verified'],
  ['OFF-09', 'stuck_pipe', 2470, 'high', 9, 'Pack-off while pulling out at 2,544 m MD; hole cleaning suspected, cuttings loading high on shakers.', 'Pumped hi-vis sweep, rotated and reamed up; tripping speed reduced.', 'Freed after 6 h; 9 h NPT.', 'DDR-OFF09-2018-03-02', 4, 0.88, 'verified'],
  ['OFF-09', 'mud_loss', 2505, 'moderate', 4, 'Seepage losses 3 m3/h increasing to 10 m3/h at 2,580 m MD.', 'LCM sweep, reduced flow rate by 10%.', 'Losses reduced to seepage; drilled ahead.', 'WCR-OFF09', 11, 0.84, 'verified'],
  ['OFF-09', 'torque_drag', 2380, 'low', 0, 'Tight spot 2,450-2,462 m MD on trip out, 15 t overpull.', 'Reamed through tight spot.', 'Clean on subsequent trip.', 'DDR-OFF09-2018-03-04', 5, 0.77, 'needs_review'],
  ['OFF-07', 'torque_drag', 2475, 'low', 0, 'Occasional torque spikes to 22 kN.m at 2,549 m MD.', 'Adjusted WOB; no further action.', 'Spikes subsided.', 'DDR-OFF07-2020-11-14', 2, 0.7, 'verified'],
  ['OFF-07', 'mud_loss', 2530, 'high', 11, 'Total losses at 2,606 m MD near the Tipam A / Tipam B boundary.', 'LCM pills, then balanced cement plug; MW reduced to 1.18 sg.', 'Returns regained; 11 h NPT.', 'WCR-OFF07', 12, 0.9, 'verified'],
  ['OFF-07', 'kick_or_overpressure', 2860, 'moderate', 2, 'Pit gain 1.6 m3 at 2,946 m MD; flow check positive.', 'Shut in, circulated out with driller’s method; MW raised to 1.32 sg.', 'Well stable after circulation.', 'DDR-OFF07-2020-11-20', 2, 0.87, 'verified'],
  ['OFF-01', 'npt', 1650, 'moderate', 3, 'Cavings on shakers and tight hole in Girujan clay.', 'MW increased 0.04 sg; inhibitor concentration raised.', 'Cavings reduced.', 'DDR-OFF01-2016-05-08', 2, 0.8, 'verified'],
  ['OFF-01', 'stuck_pipe', 1720, 'moderate', 6, 'Stuck while back-reaming in Girujan clay at 1,771 m MD.', 'Jarred down, freed; pumped sweep.', 'Freed after 4 h; 6 h NPT.', 'DDR-OFF01-2016-05-09', 3, 0.83, 'verified'],
  ['OFF-01', 'mud_loss', 2495, 'moderate', 2, 'Partial losses 5 m3/h at 2,570 m MD.', 'LCM pill.', 'Cured.', 'WCR-OFF01', 9, 0.78, 'verified'],
  ['OFF-02', 'mud_loss', 1760, 'moderate', 3, 'Partial losses in Tipam sand at 1,760 m MD.', 'LCM pill.', 'Cured.', 'WCR-OFF02', 8, 0.8, 'verified'],
  ['OFF-02', 'kick_or_overpressure', 2600, 'moderate', 3, 'Connection gas and 0.8 m3 gain in Barail at 2,600 m MD.', 'Flow check, raised MW 0.03 sg.', 'Stable.', 'DDR-OFF02-2011-10-03', 2, 0.79, 'verified'],
  ['OFF-03', 'stuck_pipe', 2410, 'moderate', 20, 'Pipe stuck in Tipam at approx. 24?0 m (scanned DDR; digit illegible).', 'Worked pipe, spotted oil-based pill.', 'Freed; 20 h NPT recorded.', 'DDR-OFF03-2008-02-17', 7, 0.52, 'needs_review'],
  ['OFF-03', 'fishing', 2415, 'high', 38, 'Twisted off BHA while working stuck pipe; fishing operations.', 'Overshot run, fish recovered on second attempt.', '38 h NPT.', 'DDR-OFF03-2008-02-18', 3, 0.6, 'needs_review'],
  ['OFF-05', 'mud_loss', 2470, 'low', 1, 'Seepage losses 2 m3/h at 2,470 m MD.', 'Continued drilling with background LCM.', 'Self-healed.', 'WCR-OFF05', 10, 0.75, 'verified'],
  ['OFF-05', 'npt', 1900, 'low', 6, 'Top drive repair.', 'Repaired on site.', '6 h NPT (equipment).', 'DDR-OFF05-2014-09-02', 1, 0.9, 'verified'],
  ['OFF-06', 'kick_or_overpressure', 3050, 'high', 12, 'Kick in Barail at 3,050 m MD; 3 m3 gain.', 'Shut in, weighted up to 1.45 sg.', '12 h NPT.', 'WCR-OFF06', 17, 0.55, 'needs_review'],
  ['OFF-08', 'torque_drag', 2400, 'moderate', 0, 'High drag in lateral section.', 'Lubricant added to mud system.', 'Drag reduced 15%.', 'DDR-OFF08-2021-06-11', 4, 0.8, 'verified'],
  ['OFF-10', 'mud_loss', 2515, 'moderate', 5, 'Partial losses 7 m3/h at 2,565 m MD.', 'LCM, reduced MW.', 'Cured after 5 h.', 'WCR-OFF10', 12, 0.72, 'verified'],
  ['OFF-10', 'cementing_issue', 2530, 'moderate', 8, 'Lost returns during 9-5/8" cement job; remedial squeeze required.', 'Squeeze cementing.', 'Zonal seal confirmed by CBL.', 'WCR-OFF10', 19, 0.7, 'verified'],
  ['OFF-11', 'stuck_pipe', 2600, 'moderate', 7, 'Differential sticking in Tipam B.', 'Spotted pill, jarred.', 'Freed; 7 h NPT.', 'DDR-OFF11-2009-04-22', 3, 0.6, 'needs_review'],
  ['OFF-12', 'npt', 1500, 'low', 1, 'Minor cavings in Girujan.', 'MW +0.02 sg.', 'Resolved.', 'DDR-OFF12-2023-02-05', 2, 0.78, 'verified'],
  ['OFF-13', 'npt', 2350, 'low', 0, 'SPP fluctuation ±15 bar; suspected washout.', 'Pulled out, found washed-out HWDP.', 'Replaced joint.', 'DDR-OFF13-2015-08-30', 2, 0.66, 'verified'],
]
const EVENTS = EVENT_ROWS.map(([wellId, type, tvd, severity, npt, raw, mitigation, outcome, report, sourcePage, confidence, verification], i) => {
  const well = wellById(wellId)
  return { id: `EVT-${101 + i}`, well_id: wellId, event_type: type, start_depth_md: mdAt(well, tvd), end_depth_md: null, tvd, tvdss: null, formation: formationAt(well, tvd),
    severity, observation: raw, cause: null, mitigation, outcome, npt_hours: npt, confidence, source_report_id: report, source_page: sourcePage, source_span: null,
    raw_phrase: raw, verification_state: verification === 'verified' ? 'verified' : 'review_needed', dataset_origin: ORIGIN }
})

// Risk look-ahead per window: probability, confidence, trend, historical/telemetry contribution.
const RISK = {
  50: { stuck_pipe: [0.58, 0.76, 'rising', 0.62, 0.38], mud_loss: [0.31, 0.66, 'steady', 0.9, 0.1], kick_or_overpressure: [0.08, 0.42, 'steady', 1, 0], torque_drag: [0.52, 0.72, 'rising', 0.45, 0.55] },
  100: { stuck_pipe: [0.72, 0.78, 'rising', 0.64, 0.36], mud_loss: [0.46, 0.68, 'rising', 0.88, 0.12], kick_or_overpressure: [0.11, 0.41, 'steady', 1, 0], torque_drag: [0.58, 0.74, 'rising', 0.42, 0.58] },
  150: { stuck_pipe: [0.69, 0.74, 'steady', 0.7, 0.3], mud_loss: [0.63, 0.7, 'rising', 0.9, 0.1], kick_or_overpressure: [0.17, 0.39, 'rising', 1, 0], torque_drag: [0.55, 0.71, 'steady', 0.44, 0.56] },
}
const HAZARD_DETAIL = {
  stuck_pipe: { wells: ['OFF-04', 'OFF-09', 'OFF-03'], factors: ['formation_match', 'historical_event_density', 'torque_trend'], evidence: ['EVT-102', 'EVT-106', 'EVT-117', 'EVT-101'],
    features: ['Surface torque +21% over the last 25 samples (rolling z = 2.4)', 'Overpull 16 t on the last connection'],
    missing: ['OFF-03 depth value has low OCR confidence (needs review)', 'No caliper log for ACTIVE-01 in this interval'],
    note: '3 analog wells with formation match; two verified stuck-pipe events 25-75 m below current TVD. Confidence reduced by one unverified source.' },
  mud_loss: { wells: ['OFF-04', 'OFF-09', 'OFF-07', 'OFF-01'], factors: ['formation_boundary_ahead', 'historical_event_density'], evidence: ['EVT-103', 'EVT-107', 'EVT-110', 'EVT-114'],
    features: ['Flow-in/flow-out differential within normal band'], missing: ['No live pit-volume channel in the replay dataset'],
    note: 'Losses cluster near the Tipam A / Tipam B boundary in four analogs. Live telemetry currently shows no loss signature.' },
  kick_or_overpressure: { wells: ['OFF-07'], factors: ['sparse_analog_evidence'], evidence: ['EVT-111'],
    features: [], missing: ['Only 1 of 3 top analogs reached Barail', 'No pore-pressure prediction supplied for ACTIVE-01'],
    note: 'Single supporting analog below the look-ahead window. Treated as low confidence; shown for completeness.' },
  torque_drag: { wells: ['OFF-04', 'OFF-09', 'OFF-07'], factors: ['torque_trend', 'trajectory_similarity', 'historical_event_density'], evidence: ['EVT-101', 'EVT-105', 'EVT-109'],
    features: ['Surface torque +21% over the last 25 samples (rolling z = 2.4)', 'Hookload drag +9 t vs. model on connections'], missing: [],
    note: 'Live torque trend and three analogs with similar J/deviated trajectories. Telemetry is the larger contributor.' },
}

// B2 semantics: historical exposure is the analog-based score; the live anomaly is a bounded additive modifier.
function hazardFor(lookahead, type) {
  const [probability, confidence, trend, , telemetryShare] = RISK[lookahead][type]
  const d = HAZARD_DETAIL[type]
  const live = telemetryShare > 0.3 ? 0.15 : 0
  return { type, assessment_id: `fx-${lookahead}-${type}`, probability, confidence, trend: trend === 'rising' ? 'rising' : 'unavailable',
    historical_exposure: round(probability - live), live_anomaly_contribution: live, supporting_offset_wells: d.wells,
    top_factors: live ? [...d.factors, 'live_anomaly'] : d.factors, evidence_ids: d.evidence,
    data_quality: { analog_count: d.wells.length, offset_quality: 0.85, evidence_quality: 0.8, telemetry_available: true, telemetry_fresh: true,
      telemetry_features: live ? { robust_z: 2.4, persistence: 3, slope: 0.0021, count: 25 } : { robust_z: 0.4, persistence: 0, slope: 0.0001, count: 25 },
      telemetry_mode: 'replay', depth_bases: ['tvd'], contradictory_evidence: false, calibration: 'unavailable', missing: d.missing } }
}
function lookaheadFrom(params) {
  const lookahead = Number(params.get('lookahead_m') || 100)
  if (!RISK[lookahead]) throw fail(422, 'lookahead_m must be 50, 100 or 150')
  return lookahead
}
function riskResponse(lookahead) {
  return { well_id: ACTIVE.id, as_of: AS_OF, current_md_m: ACTIVE.current_md_m, current_tvd_m: ACTIVE.current_tvd_m, formation: ACTIVE.current_formation, lookahead_m: lookahead,
    model_version: 'fixture-hybrid', calibrated: false, advisory_only: true, dataset_origin: ORIGIN, hazards: Object.keys(RISK[lookahead]).map(type => hazardFor(lookahead, type)) }
}
function assessmentResponse(id) {
  const [, lookahead, type] = id.match(/^fx-(\d+)-(.+)$/) || []
  if (!RISK[lookahead]?.[type]) throw fail(404, 'Assessment not found')
  const hazard = hazardFor(Number(lookahead), type)
  return { assessment_id: id, well_id: ACTIVE.id, as_of: AS_OF, current_md_m: ACTIVE.current_md_m, formation: ACTIVE.current_formation, lookahead_m: Number(lookahead),
    model_version: 'fixture-hybrid', dataset_origin: ORIGIN, hazard,
    evidence: EVENTS.filter(e => hazard.evidence_ids.includes(e.id)).map(e => ({ event: e, event_at_assessment: e, evidence_chunk_id: null,
      contribution: round(1 / hazard.evidence_ids.length), reason: `${e.well_id} analog at ${e.tvd} m TVD`, source_sha256: 'fixture', source_sha256_at_assessment: 'fixture',
      source_url: `/api/reports/${encodeURIComponent(e.source_report_id)}/source#page=${e.source_page}` })) }
}

function nearbyResponse(params) {
  const radius = Number(params.get('radius_km')) || 5
  const items = WELLS.filter(w => w.role === 'offset' && w.distance <= radius).map(w => {
    const formation = formationAt(w, ACTIVE.current_tvd_m)
    return { offset_well_id: w.id, distance_m: w.distance * 1000, distance_km: w.distance, ...Object.fromEntries(KEYS.map(key => [`${key}_score`, w.scores[key]])),
      total_score: round(KEYS.reduce((sum, key) => sum + WEIGHTS[key] * w.scores[key], 0)), depth_basis: 'tvd', weights: WEIGHTS, algorithm_version: 'fixture-hybrid',
      dataset_origin: ORIGIN, explanation: [`${w.distance} km from the active well (geographic ${w.scores.geographic.toFixed(2)})`,
        ...(formation ? [`in ${formation} at the active well's current TVD`] : []), ...(w.note ? [w.note] : [])] }
  }).sort((a, b) => b.total_score - a.total_score)
  return page(items, Number(params.get('limit')) || 50)
}

function correlationResponse(params) {
  const lookahead = lookaheadFrom(params)
  const depths = (well, tvd) => ({ md: mdAt(well, tvd), tvd, tvdss: null })
  const track = w => ({ well: wellOut(w), is_active: w.role === 'active',
    formations: w.formations.map((f, i) => ({ interval_id: `${w.id}-F${i}`, formation: f.name, top: f.top, base: f.base, confidence: f.confidence, source: 'fixture formation table', alignment_available: true })),
    events: EVENTS.filter(e => e.well_id === w.id), casing_points: w.casing.map(([size, tvd]) => ({ ...depths(w, tvd), size_in: SIZE_IN[size] ?? null, source: 'fixture casing table' })) })
  const offsets = nearbyResponse(new URLSearchParams('radius_km=20&limit=10')).items
  return { well_id: ACTIVE.id, as_of: AS_OF, dataset_origin: ORIGIN, alignment_basis: 'tvd', current_bit_depth: { md: ACTIVE.current_md_m, tvd: ACTIVE.current_tvd_m, tvdss: null },
    lookahead_window: { lookahead_m: lookahead, start: { md: ACTIVE.current_md_m, tvd: ACTIVE.current_tvd_m, tvdss: null },
      end: { md: ACTIVE.current_md_m + lookahead, tvd: Math.round(ACTIVE.current_tvd_m + lookahead * 0.95), tvdss: null } },
    warning: 'Formation analogs do not establish geological continuity. Missing datums remain unavailable.',
    tracks: [track(ACTIVE), ...offsets.map(o => track(wellById(o.offset_well_id)))] }
}

// Replay telemetry: one sample per minute over the hour before AS_OF; torque trends up in the last 15 samples. Pit volume is declared but empty.
const CHANNELS = [['ROP', 'm/h'], ['WOB', 't'], ['RPM', 'rpm'], ['torque', 'kN.m'], ['hookload', 't'], ['standpipe_pressure', 'bar'], ['flow', 'L/min'], ['mud_weight', 'sg']]
function telemetryResponse(params) {
  const count = 61
  const wave = (i, a, b) => Math.sin(i * a) * b
  const items = []
  for (let i = 0; i < count; i += 1) {
    const late = Math.max(0, i - (count - 15)) / 15
    const values = { ROP: round(14 + wave(i, 0.4, 2.2) - late * 3, 1), WOB: round(14 + wave(i, 0.23, 1.1), 1), RPM: Math.round(120 + wave(i, 0.31, 6)),
      torque: round(15.5 + wave(i, 0.5, 0.8) + late * 3.4, 2), hookload: round(142 + wave(i, 0.17, 2) + late * 4, 1),
      standpipe_pressure: Math.round(186 + wave(i, 0.27, 4) + late * 5), flow: Math.round(3350 + wave(i, 0.19, 40)), mud_weight: 1.24 }
    const timestamp = at(count - 1 - i), md = round(2438 + (12 * i) / (count - 1), 1)
    for (const [channel, unit] of CHANNELS) items.push({ well_id: ACTIVE.id, timestamp, channel, md, tvd: null, value: values[channel], unit, quality: 'good', dataset_origin: ORIGIN })
    items.push({ well_id: ACTIVE.id, timestamp, channel: 'pit_volume', md, tvd: null, value: null, unit: 'm3', quality: 'missing', dataset_origin: ORIGIN })
  }
  const channels = [...CHANNELS.map(([channel, unit]) => ({ channel, known: true, unit, sample_count: count, value_count: count, latest_timestamp: AS_OF, latest_valid_timestamp: AS_OF, state: 'fresh' })),
    { channel: 'pit_volume', known: true, unit: 'm3', sample_count: count, value_count: 0, latest_timestamp: AS_OF, latest_valid_timestamp: null, state: 'unavailable' }]
  return { ...page(items, Number(params.get('limit')) || 1000), dataset_origin: ORIGIN, source_mode: 'replay', window_start: at(60), window_end: AS_OF,
    freshness_reference: AS_OF, stale_after_seconds: 300, channels }
}

const ROUTE = 'fixture: evidence template (no model call)'
const ADVISORIES = [
  { id: 'ADV-0012', assessment_id: 'fx-100-stuck_pipe', status: 'pending_review', reviewer: null, reviewed_at: null, feedback: null, created_at: at(18),
    text: 'Two verified analogs (OFF-04, OFF-09) recorded stuck pipe 25-75 m below the current TVD in Tipam A. Live torque is trending up. Verify hole-cleaning indicators and connection overpull before the next stand; the decision rests with the drilling engineer.' },
  { id: 'ADV-0011', assessment_id: 'fx-100-mud_loss', status: 'acknowledged', reviewer: 'fixture-engineer', reviewed_at: at(80), feedback: 'Aware. LCM on standby per mud program.', created_at: at(95),
    text: 'Losses in four analogs cluster near the Tipam A / Tipam B boundary, about 138 m TVD ahead. No live loss signature at present.' },
  { id: 'ADV-0010', assessment_id: 'fx-150-kick_or_overpressure', status: 'dismissed', reviewer: 'fixture-engineer', reviewed_at: at(230), feedback: 'Only one analog; revisit before Barail.', created_at: at(240),
    text: 'Single analog kick below the look-ahead window (OFF-07, Barail). Insufficient analog coverage to support an alert.' },
].map(a => ({ ...a, model_route: ROUTE, dataset_origin: ORIGIN }))

let sequence = 5000
const AUDIT = []
function audit(action, details, actor = 'nwis-service', occurred = new Date().toISOString()) {
  sequence += 1
  AUDIT.unshift({ id: `fx-${sequence}`, chain_id: 'fixture-chain', sequence_number: sequence, occurred_at: occurred, actor_kind: actor === 'nwis-service' ? 'service' : 'user', actor_id: actor,
    event_type: 'PRODUCT_INTEGRATION_EVENT', payload: { action, product: 'SIH26121', ...details, dataset_origin: ORIGIN } })
}
audit('terms_accepted', { version: 'nwis-advisory-v1' }, 'fixture-engineer', at(700))
audit('report_ingested', { report_id: 'DDR-OFF04-2019-07-13', pages: 4 }, 'nwis-service', at(600))
audit('drilling_lesson_validation', { event_id: 'EVT-102', status: 'validated' }, 'fixture-curator', at(520))
audit('knowledge_query', { query: 'stuck pipe in Tipam', evidence: 4 }, 'fixture-engineer', at(30))
audit('risk_assessed', { well_id: 'ACTIVE-01', lookahead_m: 100 }, 'fixture-engineer', at(19))

const REVIEW_STATUSES = ['acknowledged', 'dismissed', 'reviewed']
function review(id, body) {
  const advisory = ADVISORIES.find(a => a.id === id)
  if (!advisory) throw fail(404, 'Advisory not found')
  const reason = String(body?.reason || '').trim()
  if (!REVIEW_STATUSES.includes(body?.status) || reason.length < 5) throw fail(422, 'status must be acknowledged, dismissed or reviewed, with a reason of at least 5 characters')
  if (advisory.status !== 'pending_review') throw fail(409, 'Advisory already reviewed')
  Object.assign(advisory, { status: body.status, feedback: reason, reviewer: 'fixture-engineer', reviewed_at: new Date().toISOString() })
  audit('advisory_review', { advisory_id: id, assessment_id: advisory.assessment_id, status: body.status }, 'fixture-engineer')
  return advisory
}

let queries = 0
function search(body) {
  const text = String(body?.query || '').toLowerCase()
  const range = text.match(/(\d{3,4})\s*(?:-|to)\s*(\d{3,4})/)
  const terms = text.split(/[^a-z0-9_-]+/).filter(t => t.length > 2)
  const typeHits = Object.entries({ stuck: 'stuck_pipe', loss: 'mud_loss', losses: 'mud_loss', kick: 'kick_or_overpressure', torque: 'torque_drag', casing: 'cementing_issue', cement: 'cementing_issue', fishing: 'fishing' })
    .filter(([word]) => terms.some(t => t.startsWith(word))).map(([, type]) => type)
  const formation = ['tipam', 'barail', 'girujan', 'namsang'].find(f => text.includes(f))
  const evidence = EVENTS.filter(e => !typeHits.length || typeHits.includes(e.event_type))
    .filter(e => !formation || e.formation?.toLowerCase().startsWith(formation))
    .filter(e => !range || (e.tvd >= +range[1] && e.tvd <= +range[2]))
    .filter(e => typeHits.length || formation || range || terms.some(t => e.raw_phrase.toLowerCase().includes(t)))
    .slice(0, 12)
  audit('knowledge_query', { query: body?.query?.slice(0, 120), evidence: evidence.length }, 'fixture-engineer')
  queries += 1
  return { mode: 'nwis_evidence', execution_id: `fixture-query-${queries}`, status: 'completed',
    answer: evidence.length ? `${evidence.length} cited event(s) match (fixture keyword search).` : 'No cited evidence matches this question.',
    evidence, offsets: [], risk: null, warnings: [], model_route: 'fixture keyword search (no model call)', as_of: AS_OF, dataset_origin: ORIGIN }
}

function fail(status, message) { const error = new Error(message); error.status = status; return error }
const TERMS = { version: 'nwis-advisory-v1', text: 'NWIS is an advisory prototype. Synthetic data is not Oil India data. Estimates are uncalibrated; engineering review is required. No rig control is provided.', accepted: true }

// Returns fixture data for a known NWIS path, or undefined so the request falls through to the real backend.
export function fixtureResponse(path, { method = 'GET', body } = {}) {
  const url = new URL(path, 'http://fixture.local')
  const p = url.searchParams
  const parts = url.pathname.split('/').filter(Boolean).map(decodeURIComponent)
  if (url.pathname === '/auth/me') return { id: 0, username: 'fixture-engineer', role: 'reviewer', display_name: 'Fixture engineer (dev only)', fixture: true }
  if (url.pathname === '/terms' || (url.pathname === '/terms/accept' && method === 'POST')) return TERMS
  if (parts[0] === 'wells' && parts.length === 1) return page(WELLS.map(wellOut), Number(p.get('limit')) || 50)
  if (parts[0] === 'wells' && parts[1]) {
    const well = wellById(parts[1])
    if (!well) throw fail(404, `Well ${parts[1]} not found`)
    if (parts.length === 2) return wellOut(well)
    if (parts[2] === 'formations') return page(well.formations.map(formationOut(well)), Number(p.get('limit')) || 50)
    if (well.role !== 'active' && ['risk', 'telemetry', 'nearby', 'correlation', 'assess'].includes(parts[2])) throw fail(404, `No active drilling context for ${well.id}`)
    if (parts[2] === 'nearby') return nearbyResponse(p)
    if (parts[2] === 'correlation') return correlationResponse(p)
    if (parts[2] === 'risk') return riskResponse(lookaheadFrom(p))
    if (parts[2] === 'assess' && method === 'POST') {
      const risk = riskResponse(lookaheadFrom(p))
      audit('risk_assessed', { well_id: well.id, lookahead_m: risk.lookahead_m }, 'fixture-engineer')
      return { risk, advisories: [] }
    }
    if (parts[2] === 'telemetry') return telemetryResponse(p)
  }
  if (parts[0] === 'assessments' && parts[1]) return assessmentResponse(parts[1])
  if (url.pathname === '/events') {
    const basis = p.get('depth_basis') || 'md'
    const depth = e => (basis === 'tvd' ? e.tvd : basis === 'tvdss' ? e.tvdss : e.start_depth_md)
    const min = p.get('depth_min') ? Number(p.get('depth_min')) : null
    const max = p.get('depth_max') ? Number(p.get('depth_max')) : null
    const items = EVENTS.filter(e => !p.get('well_id') || e.well_id === p.get('well_id'))
      .filter(e => !p.get('formation') || e.formation === p.get('formation')).filter(e => !p.get('type') || e.event_type === p.get('type'))
      .filter(e => (min == null && max == null) || (depth(e) != null && (min == null || depth(e) >= min) && (max == null || depth(e) <= max)))
    return page(items, Number(p.get('limit')) || 50)
  }
  if (url.pathname === '/query' && method === 'POST') return search(body)
  if (url.pathname === '/advisories') return page(ADVISORIES, Number(p.get('limit')) || 50)
  if (parts[0] === 'advisories' && parts[2] === 'review' && method === 'POST') return review(parts[1], body)
  if (url.pathname === '/audit') return page(AUDIT, Number(p.get('limit')) || 100)
  if (url.pathname === '/audit/verify') return { valid: true, events_checked: AUDIT.length, note: 'Fixture chain: not a real tamper-evidence check.' }
  return undefined
}
