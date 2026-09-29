// DEVELOPMENT FIXTURE LAYER — synthetic_demo data only. Documented in docs/nwis/frontend_fixtures.md.
// Loaded only when `import.meta.env.DEV` AND `VITE_NWIS_FIXTURES=1` (see services/api.js); a production build
// never contains this module. Nothing here is Oil India data; every record carries dataset_origin="synthetic_demo".
// It stands in for the Codex NWIS backend so screens can be built and browser-tested before integration.

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

const ACTIVE = {
  id: 'ACTIVE-01', name: 'ACTIVE-01', field: FIELD, lat: CENTER[0], lon: CENTER[1], status: 'drilling', role: 'active',
  well_type: 'development', trajectory_type: 'deviated', spud_date: '2026-08-21', td_md_m: 3250, data_quality: 0.88,
  current_md_m: 2450, current_tvd_m: 2382, current_tvdss_m: 2276, kb_elevation_m: 106, current_formation: 'TIPAM_A', hole_section: '12-1/4" intermediate',
  rig: 'Synthetic rig SR-1', trajectory_summary: 'J-shape, KOP 1,450 m MD, 18° tangent', dataset_origin: ORIGIN,
  formations: formationsFor(0, 3400, 'ACTIVE-01'),
  upcoming_formations: [{ name: 'TIPAM_B', top_tvd_m: 2520, distance_m: 138, confidence: 0.8 }, { name: 'BARAIL', top_tvd_m: 2890, distance_m: 508, confidence: 0.62 }],
  casing: [{ size: '13-3/8"', shoe_tvd_m: 1100 }, { size: '9-5/8" (planned)', shoe_tvd_m: 2500 }],
}

const WELLS = [ACTIVE, ...OFFSETS.map(([id, distance, bearing, status, type, trajectory, year, td, shift, scores, note]) => {
  const [lat, lon] = place(distance, bearing)
  return { id, name: id, field: FIELD, lat, lon, status, role: 'offset', well_type: type, trajectory_type: trajectory, spud_date: `${year}-01-15`,
    td_tvd_m: td, td_md_m: Math.round(td * MD_FACTOR[trajectory]), data_quality: scores[5], dataset_origin: ORIGIN, note: note || null,
    formations: formationsFor(shift, td, id), casing: [{ size: '13-3/8"', shoe_tvd_m: 1100 + shift }, { size: '9-5/8"', shoe_tvd_m: Math.min(td, 2500 + shift) }],
    _distance: distance, _scores: Object.fromEntries(KEYS.map((key, i) => [key, scores[i]])) }
})]
const wellById = id => WELLS.find(w => w.id === id)
const formationAt = (well, tvd) => well.formations.find(f => tvd >= f.top && tvd < f.base)?.name || null

// well, type, TVD m, severity, NPT h, source wording, mitigation, outcome, report, page, confidence, verification
const EVENT_ROWS = [
  ['OFF-04', 'torque_drag', 2428, 'moderate', 0, 'Torque erratic 18-24 kN.m while drilling 12-1/4" hole at 2,501 m MD; overpull 25 t on connection.', 'Reduced WOB to 12 t, increased flow to 3,400 L/min, back-reamed one stand.', 'Torque stabilised after two stands.', 'DDR-OFF04-2019-07-12', 3, 0.86, 'verified'],
  ['OFF-04', 'stuck_pipe', 2455, 'high', 14, 'String stuck at 2,529 m MD after connection; unable to rotate, circulation established. Suspected differential sticking across Tipam sand.', 'Spotted pipe-release pill, worked string with jar at 80 t overpull.', 'Freed after 9 h; 14 h NPT including conditioning trip.', 'DDR-OFF04-2019-07-13', 2, 0.91, 'verified'],
  ['OFF-04', 'mud_loss', 2510, 'moderate', 3, 'Partial losses 6-8 m3/h at 2,585 m MD.', 'LCM pill 40 kg/m3 medium calcium carbonate; ECD reduced by 0.03 sg.', 'Losses cured after second pill.', 'WCR-OFF04', 14, 0.82, 'verified'],
  ['OFF-04', 'cementing_issue', 2560, 'low', 2, 'Partial returns during 9-5/8" primary cement job.', 'Top-up job through annulus.', 'CBL acceptable above 2,300 m MD.', 'WCR-OFF04', 21, 0.74, 'needs_review'],
  ['OFF-09', 'torque_drag', 2440, 'moderate', 0, 'Torque rising ~20% over 30 m while drilling ahead in Tipam sand; drag trend up on connections.', 'Increased RPM to 140 and circulated bottoms-up before each connection.', 'Trend flattened; drilled ahead.', 'DDR-OFF09-2018-03-01', 3, 0.8, 'verified'],
  ['OFF-09', 'stuck_pipe', 2470, 'high', 9, 'Pack-off while pulling out at 2,544 m MD; hole cleaning suspected, cuttings loading high on shakers.', 'Pumped hi-vis sweep, rotated and reamed up; tripping speed reduced.', 'Freed after 6 h; 9 h NPT.', 'DDR-OFF09-2018-03-02', 4, 0.88, 'verified'],
  ['OFF-09', 'mud_loss', 2505, 'moderate', 4, 'Seepage losses 3 m3/h increasing to 10 m3/h at 2,580 m MD.', 'LCM sweep, reduced flow rate by 10%.', 'Losses reduced to seepage; drilled ahead.', 'WCR-OFF09', 11, 0.84, 'verified'],
  ['OFF-09', 'tight_hole', 2380, 'low', 0, 'Tight spot 2,450-2,462 m MD on trip out, 15 t overpull.', 'Reamed through tight spot.', 'Clean on subsequent trip.', 'DDR-OFF09-2018-03-04', 5, 0.77, 'needs_review'],
  ['OFF-07', 'torque_drag', 2475, 'low', 0, 'Occasional torque spikes to 22 kN.m at 2,549 m MD.', 'Adjusted WOB; no further action.', 'Spikes subsided.', 'DDR-OFF07-2020-11-14', 2, 0.7, 'verified'],
  ['OFF-07', 'mud_loss', 2530, 'high', 11, 'Total losses at 2,606 m MD near the Tipam A / Tipam B boundary.', 'LCM pills, then balanced cement plug; MW reduced to 1.18 sg.', 'Returns regained; 11 h NPT.', 'WCR-OFF07', 12, 0.9, 'verified'],
  ['OFF-07', 'kick_or_overpressure', 2860, 'moderate', 2, 'Pit gain 1.6 m3 at 2,946 m MD; flow check positive.', 'Shut in, circulated out with driller’s method; MW raised to 1.32 sg.', 'Well stable after circulation.', 'DDR-OFF07-2020-11-20', 2, 0.87, 'verified'],
  ['OFF-01', 'wellbore_instability', 1650, 'moderate', 3, 'Cavings on shakers and tight hole in Girujan clay.', 'MW increased 0.04 sg; inhibitor concentration raised.', 'Cavings reduced.', 'DDR-OFF01-2016-05-08', 2, 0.8, 'verified'],
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
  ['OFF-12', 'wellbore_instability', 1500, 'low', 1, 'Minor cavings in Girujan.', 'MW +0.02 sg.', 'Resolved.', 'DDR-OFF12-2023-02-05', 2, 0.78, 'verified'],
  ['OFF-13', 'hydraulic_anomaly', 2350, 'low', 0, 'SPP fluctuation ±15 bar; suspected washout.', 'Pulled out, found washed-out HWDP.', 'Replaced joint.', 'DDR-OFF13-2015-08-30', 2, 0.66, 'verified'],
]
const EVENTS = EVENT_ROWS.map(([wellId, type, tvd, severity, npt, raw, mitigation, outcome, report, page, confidence, verification], i) => {
  const well = wellById(wellId)
  return { id: `EVT-${101 + i}`, well_id: wellId, type, raw_observation: raw, depth_tvd_m: tvd, depth_md_m: Math.round(tvd * MD_FACTOR[well.trajectory_type]),
    formation: formationAt(well, tvd), severity, npt_hours: npt, mitigation, outcome, confidence, verification, dataset_origin: ORIGIN,
    source: { report_id: report, report_type: report.slice(0, 3), page, title: `${report.startsWith('WCR') ? 'Well Completion Report' : 'Daily Drilling Report'} · ${wellId}` } }
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

function riskResponse(lookahead) {
  const table = RISK[lookahead] || RISK[100]
  const hazards = Object.entries(table).map(([type, [probability, confidence, trend, historical, telemetry]]) => {
    const d = HAZARD_DETAIL[type]
    return { type, probability, confidence, trend, historical_contribution: historical, telemetry_contribution: telemetry,
      supporting_offset_wells: d.wells, top_factors: d.factors, evidence_ids: d.evidence, evidence_count: d.evidence.length,
      data_freshness_s: telemetry ? 20 : null, telemetry_features: d.features, missing_evidence: d.missing, confidence_explanation: d.note,
      advisory_id: ADVISORIES.find(a => a.hazard === type)?.id || null,
      trend_series: [2400, 2410, 2420, 2430, 2440, 2450].map((md, i) => ({ md_m: md, probability: +Math.max(0.02, probability - (trend === 'rising' ? 0.05 : 0.01) * (5 - i)).toFixed(2) })) }
  })
  const ids = new Set(hazards.flatMap(h => h.evidence_ids))
  return { well_id: ACTIVE.id, as_of: new Date().toISOString(), current_md_m: ACTIVE.current_md_m, current_tvd_m: ACTIVE.current_tvd_m,
    formation: ACTIVE.current_formation, lookahead_m: lookahead, window_md_m: { top: ACTIVE.current_md_m, base: ACTIVE.current_md_m + lookahead },
    model_version: 'fixture-hybrid-0.1', dataset_origin: ORIGIN, hazards, evidence: EVENTS.filter(e => ids.has(e.id)) }
}

function nearbyResponse(params) {
  const radius = Number(params.get('radius_km')) || 5
  const filters = { formation: params.get('formation'), hazard: params.get('hazard'), well_type: params.get('well_type'), trajectory_type: params.get('trajectory_type') }
  const minQuality = Number(params.get('min_quality')) || 0
  const items = WELLS.filter(w => w.role === 'offset' && w._distance <= radius && w.data_quality >= minQuality)
    .filter(w => !filters.well_type || w.well_type === filters.well_type)
    .filter(w => !filters.trajectory_type || w.trajectory_type === filters.trajectory_type)
    .filter(w => !filters.formation || w.formations.some(f => f.name === filters.formation))
    .filter(w => !filters.hazard || EVENTS.some(e => e.well_id === w.id && e.type === filters.hazard))
    .map(w => {
      const { _distance, _scores, ...well } = w
      const counts = {}
      for (const e of EVENTS) if (e.well_id === w.id) counts[e.type] = (counts[e.type] || 0) + 1
      return { well, distance_km: _distance, components: _scores, total_score: +KEYS.reduce((sum, key) => sum + WEIGHTS[key] * _scores[key], 0).toFixed(3),
        event_counts: counts, formation_at_depth: formationAt(w, ACTIVE.current_tvd_m), note: w.note }
    })
    .sort((a, b) => b.total_score - a.total_score)
    .map((item, index) => ({ ...item, rank: index + 1 }))
  return { active_well_id: ACTIVE.id, radius_km: radius, weights: WEIGHTS, formula: 'Σ wᵢ·componentᵢ (weights configurable per hazard)', as_of: new Date().toISOString(), dataset_origin: ORIGIN, items, total: items.length }
}

function correlationResponse(params) {
  const lookahead = Number(params.get('lookahead_m')) || 100
  const requested = (params.get('offsets') || '').split(',').filter(Boolean)
  const ids = requested.length ? requested : nearbyResponse(new URLSearchParams('radius_km=20')).items.slice(0, 3).map(i => i.well.id)
  const track = well => ({ well_id: well.id, name: well.name, role: well.role, td_tvd_m: well.td_tvd_m ?? null, formations: well.formations,
    casing: well.casing.map(c => ({ size: c.size, depth: c.shoe_tvd_m })),
    events: EVENTS.filter(e => e.well_id === well.id).map(e => ({ id: e.id, type: e.type, depth: e.depth_tvd_m, severity: e.severity, confidence: e.confidence, verification: e.verification, summary: e.raw_observation })) })
  return { well_id: ACTIVE.id, depth_ref: 'tvd', current_depth_m: ACTIVE.current_tvd_m, lookahead_m: lookahead,
    lookahead_window: { top: ACTIVE.current_tvd_m, base: Math.round(ACTIVE.current_tvd_m + lookahead * 0.95) }, dataset_origin: ORIGIN, as_of: new Date().toISOString(),
    tracks: [track(ACTIVE), ...ids.map(wellById).filter(Boolean).map(track)] }
}

// Replay telemetry anchored to "now" so the freshness logic can be exercised. Torque trends up in the last 25 samples.
function telemetryResponse() {
  const now = Date.now() - 20000
  const count = 120
  const wave = (i, a, b) => Math.sin(i * a) * b
  const samples = Array.from({ length: count }, (_, i) => {
    const late = Math.max(0, i - (count - 25)) / 25
    return { t: new Date(now - (count - 1 - i) * 60000).toISOString(), md_m: +(2438 + (12 * i) / (count - 1)).toFixed(1), values: {
      ROP: +(14 + wave(i, 0.4, 2.2) - late * 3).toFixed(1), WOB: +(14 + wave(i, 0.23, 1.1)).toFixed(1), RPM: Math.round(120 + wave(i, 0.31, 6)),
      TORQUE: +(15.5 + wave(i, 0.5, 0.8) + late * 3.4).toFixed(2), HKLD: +(142 + wave(i, 0.17, 2) + late * 4).toFixed(1),
      SPP: Math.round(186 + wave(i, 0.27, 4) + late * 5), FLOW: Math.round(3350 + wave(i, 0.19, 40)), MW: 1.24 } }
  })
  return { well_id: ACTIVE.id, mode: 'replay', source: 'synthetic_replay', adapter: 'replay (WITSML/ETP-ready interface)', as_of: samples.at(-1).t, stale_after_s: 120,
    dataset_origin: ORIGIN, samples, channels: [
      { mnemonic: 'ROP', label: 'ROP', unit: 'm/h', quality: 'ok' }, { mnemonic: 'WOB', label: 'WOB', unit: 't', quality: 'ok' },
      { mnemonic: 'RPM', label: 'RPM', unit: 'rpm', quality: 'ok' }, { mnemonic: 'TORQUE', label: 'Torque', unit: 'kN·m', quality: 'ok' },
      { mnemonic: 'HKLD', label: 'Hookload', unit: 't', quality: 'ok' }, { mnemonic: 'SPP', label: 'Standpipe pressure', unit: 'bar', quality: 'ok' },
      { mnemonic: 'FLOW', label: 'Flow in', unit: 'L/min', quality: 'ok' }, { mnemonic: 'MW', label: 'Mud weight', unit: 'sg', quality: 'ok' },
      { mnemonic: 'PIT', label: 'Pit volume', unit: 'm3', quality: 'missing' }] } // declared but absent: must not be drawn
}

const minutesAgo = m => new Date(Date.now() - m * 60000).toISOString()
const ADVISORIES = [
  { id: 'ADV-0012', well_id: 'ACTIVE-01', hazard: 'stuck_pipe', status: 'open', severity: 'warning', probability: 0.72, confidence: 0.78, lookahead_m: 100,
    interval_md_m: { top: 2450, base: 2550 }, formation: 'TIPAM_A', created_at: minutesAgo(18), evidence_ids: ['EVT-102', 'EVT-106', 'EVT-101'],
    summary: 'Two verified analogs (OFF-04, OFF-09) recorded stuck pipe 25-75 m below the current TVD in Tipam A. Live torque is trending up. Verify hole-cleaning indicators and connection overpull before the next stand; the decision rests with the drilling engineer.',
    historical_response: ['OFF-04: pipe-release pill and jarring; freed after 9 h (DDR-OFF04-2019-07-13 p.2)', 'OFF-09: hi-vis sweep, reamed up, reduced tripping speed; freed after 6 h (DDR-OFF09-2018-03-02 p.4)'],
    model_route: 'fixture: evidence template (no model call)', reviews: [] },
  { id: 'ADV-0011', well_id: 'ACTIVE-01', hazard: 'mud_loss', status: 'acknowledged', severity: 'advisory', probability: 0.46, confidence: 0.68, lookahead_m: 100,
    interval_md_m: { top: 2450, base: 2550 }, formation: 'TIPAM_A', created_at: minutesAgo(95), evidence_ids: ['EVT-103', 'EVT-107', 'EVT-110'],
    summary: 'Losses in four analogs cluster near the Tipam A / Tipam B boundary, about 138 m TVD ahead. No live loss signature at present.',
    historical_response: ['OFF-04: LCM 40 kg/m3 calcium carbonate, ECD reduced (WCR-OFF04 p.14)', 'OFF-07: LCM then cement plug; MW reduced (WCR-OFF07 p.12)'],
    model_route: 'fixture: evidence template (no model call)', reviews: [{ reviewer: 'fixture-engineer', at: minutesAgo(80), decision: 'acknowledge', feedback: 'useful', note: 'Aware. LCM on standby per mud program.' }] },
  { id: 'ADV-0010', well_id: 'ACTIVE-01', hazard: 'kick_or_overpressure', status: 'insufficient_evidence', severity: 'advisory', probability: 0.11, confidence: 0.41, lookahead_m: 150,
    interval_md_m: { top: 2400, base: 2550 }, formation: 'TIPAM_A', created_at: minutesAgo(240), evidence_ids: ['EVT-111'],
    summary: 'Single analog kick below the look-ahead window (OFF-07, Barail). Insufficient analog coverage to support an alert.',
    historical_response: ['OFF-07: shut in, driller’s method, MW raised to 1.32 sg (DDR-OFF07-2020-11-20 p.2)'],
    model_route: 'fixture: evidence template (no model call)', reviews: [{ reviewer: 'fixture-engineer', at: minutesAgo(230), decision: 'insufficient_evidence', feedback: 'insufficient_evidence', note: 'Only one analog; revisit before Barail.' }] },
]

let sequence = 5000
const AUDIT = []
function audit(type, details, actor = 'nwis-service', at = new Date().toISOString()) {
  sequence += 1
  AUDIT.unshift({ id: `fx-${sequence}`, sequence_number: sequence, event_type: type.toUpperCase(), occurred_at: at, actor_kind: actor === 'nwis-service' ? 'service' : 'user', actor_id: actor, details: { ...details, dataset_origin: ORIGIN } })
}
audit('report_ingested', { report_id: 'DDR-OFF04-2019-07-13', parser: 'layout-v2', pages: 4 }, 'nwis-service', minutesAgo(600))
audit('event_extracted', { event_id: 'EVT-102', report_id: 'DDR-OFF04-2019-07-13', page: 2, confidence: 0.91 }, 'nwis-service', minutesAgo(598))
audit('event_validated', { event_id: 'EVT-102', decision: 'verified' }, 'fixture-curator', minutesAgo(520))
audit('offset_query', { well_id: 'ACTIVE-01', radius_km: 5, results: 6 }, 'fixture-engineer', minutesAgo(30))
audit('risk_assessment', { well_id: 'ACTIVE-01', lookahead_m: 100, model_version: 'fixture-hybrid-0.1' }, 'nwis-service', minutesAgo(19))
audit('alert_created', { advisory_id: 'ADV-0012', hazard: 'stuck_pipe', evidence_ids: ['EVT-102', 'EVT-106'] }, 'nwis-service', minutesAgo(18))

const DECISIONS = { acknowledge: 'acknowledged', review: 'reviewed', insufficient_evidence: 'insufficient_evidence', note: null }
function review(id, body) {
  const advisory = ADVISORIES.find(a => a.id === id)
  if (!advisory) throw fail(404, 'Advisory not found')
  if (!Object.hasOwn(DECISIONS, body?.decision)) throw fail(422, 'decision must be acknowledge, review, insufficient_evidence or note')
  if (String(body.note || '').trim().length < 5) throw fail(422, 'An engineering note of at least 5 characters is required')
  advisory.reviews.push({ reviewer: 'fixture-engineer', at: new Date().toISOString(), decision: body.decision, feedback: body.feedback || null, note: body.note.trim() })
  if (DECISIONS[body.decision]) advisory.status = DECISIONS[body.decision]
  audit(body.decision === 'acknowledge' ? 'alert_acknowledged' : 'advisory_reviewed', { advisory_id: id, decision: body.decision, feedback: body.feedback || null }, 'fixture-engineer')
  return advisory
}

function search(body) {
  const text = String(body?.query || '').toLowerCase()
  const range = text.match(/(\d{3,4})\s*(?:-|to)\s*(\d{3,4})/)
  const terms = text.split(/[^a-z0-9_-]+/).filter(t => t.length > 2)
  const typeHits = Object.entries({ stuck: 'stuck_pipe', loss: 'mud_loss', losses: 'mud_loss', kick: 'kick_or_overpressure', torque: 'torque_drag', casing: 'cementing_issue', cement: 'cementing_issue', fishing: 'fishing' })
    .filter(([word]) => terms.some(t => t.startsWith(word))).map(([, type]) => type)
  const formation = ['tipam', 'barail', 'girujan', 'namsang'].find(f => text.includes(f))
  const events = EVENTS.filter(e => !typeHits.length || typeHits.includes(e.type))
    .filter(e => !formation || e.formation?.toLowerCase().startsWith(formation))
    .filter(e => !range || (e.depth_tvd_m >= +range[1] && e.depth_tvd_m <= +range[2]))
    .filter(e => typeHits.length || formation || range || terms.some(t => e.raw_observation.toLowerCase().includes(t)))
    .slice(0, 12)
  const results = [
    ...[...new Set(events.map(e => e.well_id))].map(id => { const w = wellById(id); return { kind: 'well', well_id: id, title: id, excerpt: `${w.trajectory_type} ${w.well_type} well · ${events.filter(e => e.well_id === id).length} matching events`, confidence: w.data_quality, verification: 'catalogue' } }),
    ...events.map(e => ({ kind: 'event', event_id: e.id, well_id: e.well_id, title: `${e.id} · ${e.type}`, excerpt: e.raw_observation, depth_tvd_m: e.depth_tvd_m, depth_md_m: e.depth_md_m, formation: e.formation, confidence: e.confidence, verification: e.verification, source: e.source, mitigation: e.mitigation })),
    ...[...new Map(events.map(e => [e.source.report_id, e])).values()].map(e => ({ kind: 'report', report_id: e.source.report_id, well_id: e.well_id, title: e.source.title, excerpt: e.raw_observation, page: e.source.page, formation: e.formation, depth_tvd_m: e.depth_tvd_m, confidence: e.confidence, verification: e.verification, source: e.source })),
  ]
  audit('offset_query', { query: body?.query?.slice(0, 120), results: results.length }, 'fixture-engineer')
  return { query: body?.query, mode: 'fixture keyword search (no model call)', dataset_origin: ORIGIN, results }
}

function fail(status, message) { const error = new Error(message); error.status = status; return error }
const strip = ({ _distance, _scores, ...well }) => well // eslint-disable-line no-unused-vars

// Returns fixture data for a known NWIS path, or undefined so the request falls through to the real backend.
export function fixtureResponse(path, { method = 'GET', body } = {}) {
  const url = new URL(path, 'http://fixture.local')
  const p = url.searchParams
  const parts = url.pathname.split('/').filter(Boolean).map(decodeURIComponent)
  if (url.pathname === '/auth/me') return { id: 0, username: 'fixture-engineer', role: 'reviewer', display_name: 'Fixture engineer (dev only)', fixture: true }
  if (parts[0] === 'wells' && parts.length === 1) {
    const q = (p.get('q') || '').toLowerCase()
    const items = WELLS.filter(w => !q || w.id.toLowerCase().includes(q)).filter(w => !p.get('status') || w.status === p.get('status')).map(strip)
    return { items, total: items.length, dataset_origin: ORIGIN }
  }
  if (parts[0] === 'wells' && parts[1]) {
    const well = wellById(parts[1])
    if (!well) throw fail(404, `Well ${parts[1]} not found`)
    if (parts.length === 2) return strip(well)
    if (well.role !== 'active' && ['risk', 'telemetry', 'nearby', 'correlation'].includes(parts[2])) throw fail(404, `No active drilling context for ${well.id}`)
    if (parts[2] === 'nearby') return nearbyResponse(p)
    if (parts[2] === 'correlation') return correlationResponse(p)
    if (parts[2] === 'risk') return riskResponse(Number(p.get('lookahead_m')) || 100)
    if (parts[2] === 'telemetry') return telemetryResponse()
  }
  if (url.pathname === '/events') {
    const ids = (p.get('ids') || '').split(',').filter(Boolean)
    const wells = (p.get('well_id') || '').split(',').filter(Boolean)
    const min = p.get('depth_min') ? Number(p.get('depth_min')) : -Infinity
    const max = p.get('depth_max') ? Number(p.get('depth_max')) : Infinity
    const items = EVENTS.filter(e => !ids.length || ids.includes(e.id)).filter(e => !wells.length || wells.includes(e.well_id))
      .filter(e => !p.get('formation') || e.formation === p.get('formation')).filter(e => !p.get('type') || e.type === p.get('type'))
      .filter(e => !p.get('severity') || e.severity === p.get('severity')).filter(e => e.depth_tvd_m >= min && e.depth_tvd_m <= max)
    return { items: items.slice(0, Number(p.get('limit')) || 100), total: items.length, dataset_origin: ORIGIN }
  }
  if (url.pathname === '/query' && method === 'POST') return search(body)
  if (url.pathname === '/advisories') return { items: ADVISORIES, total: ADVISORIES.length, dataset_origin: ORIGIN }
  if (parts[0] === 'advisories' && parts[2] === 'review' && method === 'POST') return review(parts[1], body)
  if (url.pathname === '/audit/log') return AUDIT.slice(0, Number(p.get('limit')) || 100)
  if (url.pathname === '/audit/verify') return { valid: true, events_checked: AUDIT.length, note: 'Fixture chain: not a real tamper-evidence check.' }
  return undefined
}
