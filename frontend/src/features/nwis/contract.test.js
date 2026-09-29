import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { createServer } from 'vite'
import { validateContract } from './contract.js'
import { LEGACY_QUERY_RESPONSE, SAMPLES } from './contractSamples.js'
import { fixtureResponse } from './fixtures.js'
import { adaptAdvisory, adaptAuditList, adaptCorrelation, adaptEvent, adaptEventList, adaptNearby, adaptQuery, adaptRisk, adaptTelemetry, adaptWell, adaptWellList } from './adapters.js'

const CASES = [['well', 'well'], ['nearby', 'nearby'], ['correlation', 'correlation'], ['event', null], ['risk', 'risk'], ['telemetry', 'telemetry'], ['query', 'query'], ['advisory', 'advisory'], ['audit', 'auditList']]

test('schema samples (full and sparse) satisfy the frontend contract', () => {
  for (const [sample, contract] of CASES) for (const variant of ['full', 'sparse']) {
    const data = SAMPLES[sample][variant]
    const problems = contract ? validateContract(contract, data) : validateContract('eventList', [data])
    assert.deepEqual(problems, [], `${sample}.${variant}`)
  }
})

test('development fixtures stay in sync with the contract', () => {
  const check = (contract, path, options) => assert.deepEqual(validateContract(contract, fixtureResponse(path, options)), [], path)
  check('wellList', '/wells')
  check('well', '/wells/ACTIVE-01')
  check('nearby', '/wells/ACTIVE-01/nearby?radius_km=20')
  check('correlation', '/wells/ACTIVE-01/correlation?lookahead_m=100')
  check('eventList', '/events')
  for (const lookahead of [50, 100, 150]) check('risk', `/wells/ACTIVE-01/risk?lookahead_m=${lookahead}`)
  check('telemetry', '/wells/ACTIVE-01/telemetry')
  check('query', '/query', { method: 'POST', body: { query: 'stuck pipe in Tipam between 2400-2700 m TVD' } })
  check('advisoryList', '/advisories')
  check('auditList', '/audit/log')
})

test('the validator reports contract violations precisely', () => {
  assert.deepEqual(validateContract('well', { name: 'x' }), ['well.id: required str is missing'])
  assert.match(validateContract('risk', { as_of: 'x', lookahead_m: 100, hazards: [{ type: 'stuck_pipe', probability: '72%' }] })[0], /hazards\[0\]\.probability: expected num/)
  assert.match(validateContract('nearby', { items: [{ rank: 2, well: { id: 'A' }, components: {} }, { rank: 1, well: { id: 'B' }, components: {} }] }).at(-1), /rank order/)
  assert.deepEqual(validateContract('eventList', { rows: [] }), ['eventList: expected an array or { items: [] }'])
  assert.match(validateContract('query', { results: [{ kind: 'chunk' }] })[0], /well \| event \| report/)
})

test('adapters keep missing values null — never 0', () => {
  const well = adaptWell(SAMPLES.well.sparse)
  assert.equal(well.current_tvdss_m, null)
  assert.equal(well.data_quality, null)
  assert.equal(well.name, 'OFF-99', 'name falls back to id, never blank')
  assert.deepEqual(well.formations[0], { name: 'TIPAM_B', top: null, base: 2890, confidence: null, interpreted: false })
  const event = adaptEvent(SAMPLES.event.sparse)
  for (const key of ['npt_hours', 'mitigation', 'outcome', 'depth_md_m', 'confidence', 'formation']) assert.equal(event[key], null, key)
  assert.equal(event.source.page, null)
  const hazard = adaptRisk(SAMPLES.risk.sparse).hazards[0]
  assert.equal(hazard.probability, null)
  assert.equal(hazard.evidenceCount, null, 'unreported evidence is not "0 records"')
  assert.deepEqual(adaptRisk(SAMPLES.risk.sparse).evidence, [])
  assert.equal(adaptNearby(SAMPLES.nearby.sparse).items.length, 0)
  const telemetry = adaptTelemetry(SAMPLES.telemetry.full)
  assert.deepEqual(telemetry.series.map(s => s.id), ['TORQUE'])
  assert.deepEqual(telemetry.missing.map(c => c.mnemonic), ['PIT'])
  assert.equal(adaptTelemetry(SAMPLES.telemetry.sparse).series.length, 0)
  const advisory = adaptAdvisory(SAMPLES.advisory.sparse)
  assert.equal(advisory.interval_md_m, null)
  assert.equal(advisory.probability, null)
  assert.equal(adaptCorrelation(SAMPLES.correlation.sparse).lookahead_window, null)
  assert.equal(adaptCorrelation(SAMPLES.correlation.sparse).tracks[0].events[0].depth, null)
})

test('adapters absorb plausible backend field-name variants in one place', () => {
  const well = adaptWell({ well_id: 'W-1', well_name: 'Well 1', latitude: 27.1, longitude: 95.2, formation_intervals: [{ formation: 'TIPAM_A', top_tvd_m: 2100, base_tvd_m: 2500 }] })
  assert.deepEqual([well.id, well.name, well.lat, well.lon, well.formations[0].name, well.formations[0].top], ['W-1', 'Well 1', 27.1, 95.2, 'TIPAM_A', 2100])
  assert.deepEqual([adaptWell({ id: 'G', location: { type: 'Point', coordinates: [95.5, 27.5] } }).lat, adaptWell({ id: 'G', location: { coordinates: [95.5, 27.5] } }).lon], [27.5, 95.5])
  const event = adaptEvent({ event_id: 'E', well_id: 'W', event_type: 'mud_loss', source_text: 'Losses', md_m: 2500, report_id: 'DDR-1', page: 4 })
  assert.deepEqual([event.id, event.type, event.raw_observation, event.depth_md_m, event.source.report_id, event.source.page], ['E', 'mud_loss', 'Losses', 2500, 'DDR-1', 4])
  const hazard = adaptRisk({ hazards: [{ hazard_type: 'stuck_pipe', supporting_wells: [{ well_id: 'OFF-04' }], evidence: [{ id: 'EVT-1' }, { id: 'EVT-2' }] }] }).hazards[0]
  assert.deepEqual([hazard.type, hazard.wells, hazard.evidenceIds, hazard.evidenceCount], ['stuck_pipe', ['OFF-04'], ['EVT-1', 'EVT-2'], 2])
  assert.deepEqual(adaptWellList([{ id: 'A' }]).items.map(w => w.id), ['A'], 'bare arrays and envelopes both work')
  assert.equal(adaptEventList({ items: [], total: 12 }).total, 12)
  assert.equal(adaptAuditList([{ sequence_number: 1, event_type: 'X', payload: { a: 1 } }]).items[0].details.a, 1)
})

test('POST /query: only an NWIS results list is treated as evidence; a legacy governed response is flagged', () => {
  const nwis = adaptQuery(SAMPLES.query.full)
  assert.equal(nwis.recognized, true)
  assert.deepEqual(nwis.results.map(r => r.kind), ['event', 'report'])
  assert.equal(nwis.results[1].page, null)
  const legacy = adaptQuery(LEGACY_QUERY_RESPONSE)
  assert.equal(legacy.recognized, false)
  assert.deepEqual(legacy.results, [])
  assert.equal(adaptQuery({ results: [{ kind: 'chunk', source: { report_id: 'R', page: 3 } }] }).results[0].kind, 'report')
  assert.equal(adaptQuery({ results: [{ kind: 'event', source: { report_id: 'R', page: 3 } }] }).results[0].page, 3)
})

test('domain components render full and sparse contract data without crashing or inventing zeros', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { RiskCard, OffsetScoreBreakdown, EvidenceDrawer, EventDots } = await server.ssrLoadModule('/src/features/nwis/components.jsx')
    const { default: CorrelationTracks } = await server.ssrLoadModule('/src/features/nwis/CorrelationTracks.jsx')
    const { EventCard } = await server.ssrLoadModule('/src/features/nwis/pages/IntelligencePages.jsx')
    const render = element => renderToStaticMarkup(createElement(MemoryRouter, null, element))

    const fullRisk = adaptRisk(SAMPLES.risk.full)
    assert.match(render(createElement(RiskCard, { hazard: fullRisk.hazards[0], lookahead: 100, onWhy: () => {} })), /72%.*Why this alert\?/s)
    const sparseCard = render(createElement(RiskCard, { hazard: adaptRisk(SAMPLES.risk.sparse).hazards[0], lookahead: 150 }))
    assert.match(sparseCard, /Not reported/)
    assert.doesNotMatch(sparseCard, /0 records|>0%</)
    assert.match(sparseCard, /data-level="unknown"/)
    render(createElement(EvidenceDrawer, { hazard: fullRisk.hazards[0], risk: fullRisk, offsets: adaptNearby(SAMPLES.nearby.full).items }))
    render(createElement(EvidenceDrawer, { hazard: adaptRisk(SAMPLES.risk.sparse).hazards[0], risk: adaptRisk(SAMPLES.risk.sparse) }))

    const sparseEvent = render(createElement(EventCard, { event: adaptEvent(SAMPLES.event.sparse) }))
    assert.match(sparseEvent, /No source wording stored/)
    assert.doesNotMatch(sparseEvent, /0 h|page 0/)
    assert.match(render(createElement(EventCard, { event: adaptEvent(SAMPLES.event.full) })), /DDR-OFF04-2019-07-13.*page 2/s)

    const offset = adaptNearby(SAMPLES.nearby.full).items[0]
    assert.match(render(createElement(OffsetScoreBreakdown, { offset: { ...offset, components: { ...offset.components, program: null } } })), /—/)
    assert.match(render(createElement(EventDots, { counts: {} })), /None/)

    render(createElement(CorrelationTracks, { data: adaptCorrelation(SAMPLES.correlation.full) }))
    const sparseCorrelation = render(createElement(CorrelationTracks, { data: adaptCorrelation(SAMPLES.correlation.sparse) }))
    assert.match(sparseCorrelation, /No correlation tracks returned|unknown/)
  } finally { await server.close() }
})
