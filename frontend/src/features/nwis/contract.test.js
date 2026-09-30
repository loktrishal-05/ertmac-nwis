import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { createServer } from 'vite'
import { validateContract } from './contract.js'
import { LEGACY_QUERY_RESPONSE, SAMPLES } from './contractSamples.js'
import { fixtureResponse } from './fixtures.js'
import { adaptAdvisory, adaptAssessment, adaptAuditList, adaptCorrelation, adaptEvent, adaptNearby, adaptQuery, adaptRisk, adaptTelemetry, adaptWell, groupResults } from './adapters.js'

const PAGE = { limit: 100, offset: 0, has_more: false, as_of: null }
const CASES = [['well', 'well'], ['nearby', 'nearby'], ['correlation', 'correlation'], ['event', 'eventList'], ['risk', 'risk'], ['assessment', 'assessment'],
  ['telemetry', 'telemetry'], ['query', 'query'], ['advisory', 'advisoryList'], ['audit', 'auditList']]
const LISTED = new Set(['event', 'advisory']) // single-item samples validated inside a B2 page

test('B2 schema samples (full and sparse) satisfy the frontend contract', () => {
  for (const [sample, contract] of CASES) for (const variant of ['full', 'sparse']) {
    const data = SAMPLES[sample][variant]
    assert.deepEqual(validateContract(contract, LISTED.has(sample) ? { ...PAGE, items: [data] } : data), [], `${sample}.${variant}`)
  }
})

test('development fixtures emit the same B2 contract', () => {
  const check = (contract, path, options) => assert.deepEqual(validateContract(contract, fixtureResponse(path, options)), [], path)
  check('wellList', '/wells?limit=100')
  check('well', '/wells/ACTIVE-01')
  check('formationList', '/wells/ACTIVE-01/formations?limit=100')
  check('nearby', '/wells/ACTIVE-01/nearby?radius_km=20')
  check('correlation', '/wells/ACTIVE-01/correlation?lookahead_m=100')
  check('eventList', '/events?limit=100')
  for (const lookahead of [50, 100, 150]) check('risk', `/wells/ACTIVE-01/risk?lookahead_m=${lookahead}`)
  check('assessment', '/assessments/fx-100-stuck_pipe')
  check('telemetry', '/wells/ACTIVE-01/telemetry?limit=1000')
  check('query', '/query', { method: 'POST', body: { query: 'stuck pipe in Tipam between 2400-2700 m TVD', mode: 'nwis_evidence' } })
  check('advisoryList', '/advisories?limit=100')
  check('auditList', '/audit?limit=100')
  check('terms', '/terms')
})

test('the validator reports contract violations precisely', () => {
  assert.ok(validateContract('well', { name: 'x' }).includes('well.id: required str is missing'))
  const bad = { ...SAMPLES.risk.full, hazards: [{ ...SAMPLES.risk.full.hazards[0], probability: '72%' }] }
  assert.match(validateContract('risk', bad)[0], /hazards\[0\]\.probability: expected num/)
  const unordered = { ...PAGE, items: [{ ...SAMPLES.nearby.full.items[0], total_score: 0.5 }, { ...SAMPLES.nearby.full.items[0], total_score: 0.9 }] }
  assert.match(validateContract('nearby', unordered).at(-1), /ranking order/)
  assert.deepEqual(validateContract('eventList', { rows: [] }), ['eventList: expected { items: [] }'])
})

test('adapters keep missing values null — never 0', () => {
  const well = adaptWell(SAMPLES.well.sparse)
  for (const key of ['lat', 'lon', 'td_md_m', 'current_md_m', 'field']) assert.equal(well[key], null, key)
  assert.equal(well.role, null, 'a historical well is not the active well')
  const event = adaptEvent(SAMPLES.event.sparse)
  for (const key of ['npt_hours', 'mitigation', 'outcome', 'depth_md_m', 'confidence', 'formation', 'raw_observation']) assert.equal(event[key], null, key)
  assert.deepEqual([event.source.page, event.source.url], [null, '/api/reports/OFF-03-DDR/source'])
  const hazard = adaptRisk(SAMPLES.risk.sparse).hazards[0]
  for (const key of ['probability', 'historical', 'telemetry', 'trend']) assert.equal(hazard[key], null, key)
  assert.deepEqual([hazard.evidenceCount, hazard.telemetryState, hazard.missing], [0, 'unavailable', ['analog_offsets']])
  assert.equal(adaptRisk(SAMPLES.risk.sparse).window_md_m, null)
  assert.equal(adaptNearby(SAMPLES.nearby.sparse).items.length, 0)
  const telemetry = adaptTelemetry(SAMPLES.telemetry.full)
  assert.deepEqual([telemetry.series.map(s => s.id), telemetry.missing.map(c => c.mnemonic), telemetry.state], [['torque'], ['pit_volume'], 'partial'])
  assert.deepEqual([adaptTelemetry(SAMPLES.telemetry.sparse).series.length, adaptTelemetry(SAMPLES.telemetry.sparse).state], [0, 'unknown'])
  const advisory = adaptAdvisory(SAMPLES.advisory.sparse)
  assert.deepEqual([advisory.reviewer, advisory.reviewed_at, advisory.reason], [null, null, null])
  const correlation = adaptCorrelation(SAMPLES.correlation.sparse)
  assert.equal(correlation.lookahead_window, null)
  assert.deepEqual([correlation.tracks[0].events[0].depth, correlation.tracks[0].formations[0].top, correlation.tracks[0].formations[0].available], [null, null, false])
  assert.deepEqual(adaptAssessment(SAMPLES.assessment.sparse).evidence, [])
})

test('adapters map B2 field names in one place', () => {
  const active = adaptWell(SAMPLES.well.full)
  assert.deepEqual([active.role, active.lat, active.lon, active.td_md_m, active.current_md_m], ['active', 27.4, 95.3, 3200, 2450])
  const nearby = adaptNearby(SAMPLES.nearby.full)
  const top = nearby.items[0]
  assert.deepEqual([top.id, top.rank, top.distanceKm, top.components.formation, top.components.data_quality, top.depthBasis, top.explanation.length], ['OFF-04', 1, 1.5473, 1, 0.95, 'tvd', 2])
  assert.equal(nearby.items[1].components.program, null)
  assert.equal(nearby.weights.formation, 0.3, 'weights come from the backend match items')
  const event = adaptEvent(SAMPLES.event.full)
  assert.deepEqual([event.type, event.depth_md_m, event.depth_tvd_m, event.verification, event.source.url], ['stuck_pipe', 2410, 2410, 'unverified', '/api/reports/OFF-04-DDR/source#page=1'])
  assert.match(event.raw_observation, /^Well: OFF-04/)
  const risk = adaptRisk(SAMPLES.risk.full)
  assert.deepEqual([risk.calibrated, risk.advisory_only, risk.window_md_m], [false, true, { top: 2450, base: 2550 }])
  const hazard = risk.hazards[0]
  assert.deepEqual([hazard.assessmentId, hazard.historical, hazard.telemetry, hazard.telemetryState, hazard.telemetryFeatures.length], ['a1b2c3', 0.7, 0.15, 'fresh', 3])
  assert.match(hazard.confidenceNote, /10 analog wells.*telemetry fresh \(replay\)/)
  const link = adaptAssessment(SAMPLES.assessment.full).evidence[0]
  assert.deepEqual([link.sourceHashMatches, link.changedSinceAssessment, link.sourceUrl], [true, false, '/api/reports/OFF-04-DDR/source#page=1'])
  const correlation = adaptCorrelation(SAMPLES.correlation.full)
  assert.deepEqual([correlation.depth_ref, correlation.current_depth_m, correlation.lookahead_window], ['tvd', 2450, { top: 2450, base: 2550 }])
  assert.deepEqual(correlation.tracks.map(t => t.role), ['active', 'offset'])
  assert.deepEqual(correlation.tracks[1].casing, [{ size: '13.375"', depth: 1100 }])
  const audit = adaptAuditList(SAMPLES.audit.full).items[0]
  assert.equal(audit.event_type, 'advisory_review')
  assert.ok(!('product' in audit.details) && !('action' in audit.details))
})

test('POST /api/query: only an nwis_evidence answer with evidence[] is treated as evidence; a legacy governed response is flagged', () => {
  const nwis = adaptQuery(SAMPLES.query.full)
  assert.deepEqual([nwis.recognized, nwis.status, nwis.summary, nwis.citations], [true, 'completed', 'Two cited stuck-pipe events in TIPAM_A.', ['EVT-d425ce494054e5fa', 'EVT-2']])
  const groups = groupResults(nwis)
  assert.deepEqual([groups.well.length, groups.event.length, groups.report.length], [1, 2, 2])
  const refused = adaptQuery(SAMPLES.query.sparse)
  assert.deepEqual([refused.recognized, refused.status, refused.results], [true, 'refused', []])
  const legacy = adaptQuery(LEGACY_QUERY_RESPONSE)
  assert.deepEqual([legacy.recognized, legacy.results], [false, []])
})

test('domain components render full and sparse contract data without crashing or inventing zeros', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { RiskCard, OffsetScoreBreakdown, EvidenceDrawer, EventDots } = await server.ssrLoadModule('/src/features/nwis/components.jsx')
    const { default: CorrelationTracks } = await server.ssrLoadModule('/src/features/nwis/CorrelationTracks.jsx')
    const { EventCard } = await server.ssrLoadModule('/src/features/nwis/pages/IntelligencePages.jsx')
    const render = element => renderToStaticMarkup(createElement(MemoryRouter, null, element))

    const fullRisk = adaptRisk(SAMPLES.risk.full)
    assert.match(render(createElement(RiskCard, { hazard: fullRisk.hazards[0], lookahead: 100, onWhy: () => {} })), /75%.*uncalibrated estimate.*Why this alert\?/s)
    const sparseRisk = adaptRisk(SAMPLES.risk.sparse)
    const sparseCard = render(createElement(RiskCard, { hazard: sparseRisk.hazards[0], lookahead: 150 }))
    assert.match(sparseCard, /Insufficient evidence/)
    assert.doesNotMatch(sparseCard, />0%</)
    assert.match(sparseCard, /data-level="unknown"/)
    render(createElement(EvidenceDrawer, { hazard: fullRisk.hazards[0], risk: fullRisk, offsets: adaptNearby(SAMPLES.nearby.full).items, wellId: 'ACTIVE-01' }))
    render(createElement(EvidenceDrawer, { hazard: sparseRisk.hazards[0], risk: sparseRisk }))

    const sparseEvent = render(createElement(EventCard, { event: adaptEvent(SAMPLES.event.sparse) }))
    assert.match(sparseEvent, /No source wording stored/)
    assert.doesNotMatch(sparseEvent, /0 h|page 0/)
    assert.match(render(createElement(EventCard, { event: adaptEvent(SAMPLES.event.full) })), /href="\/api\/reports\/OFF-04-DDR\/source#page=1".*OFF-04-DDR.*page 1/s)

    const offset = adaptNearby(SAMPLES.nearby.full).items[1]
    assert.match(render(createElement(OffsetScoreBreakdown, { offset })), /—/)
    assert.match(render(createElement(EventDots, { counts: {} })), /—/)

    render(createElement(CorrelationTracks, { data: adaptCorrelation(SAMPLES.correlation.full) }))
    render(createElement(CorrelationTracks, { data: adaptCorrelation(SAMPLES.correlation.sparse) }))
  } finally { await server.close() }
})
