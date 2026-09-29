import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { closestExplanation, freshness, isSynthetic, listOf, paths, riskLevel, safeDetails } from './nwisModel.js'
import { adaptQuery, groupResults, normalizeHazard, rankedOffsets, telemetrySeries } from './adapters.js'
import { fixtureResponse } from './fixtures.js'

test('API paths are same-origin relative, encoded and never hard-code a host', () => {
  assert.equal(paths.nearby('ACTIVE 01', { radius_km: 5, formation: '' }), '/wells/ACTIVE%2001/nearby?radius_km=5')
  assert.equal(paths.risk('ACTIVE-01', 100), '/wells/ACTIVE-01/risk?lookahead_m=100')
  assert.equal(paths.correlation('A', { offsets: ['OFF-04', 'OFF-09'], lookahead_m: 100 }), '/wells/A/correlation?offsets=OFF-04%2COFF-09&lookahead_m=100')
  assert.equal(paths.events({ well_id: 'OFF-04' }), '/events?limit=100&well_id=OFF-04')
  for (const path of [paths.wells(), paths.well('X'), paths.telemetry('X'), paths.advisories(), paths.audit(), paths.query]) assert.match(path, /^\/[a-z]/)
})

test('backend ranking is authoritative and a closer irrelevant well is explained, not re-ranked', () => {
  const offsets = rankedOffsets(fixtureResponse('/wells/ACTIVE-01/nearby?radius_km=5'))
  assert.deepEqual(offsets.map(o => o.rank), offsets.map((_, i) => i + 1))
  assert.equal(offsets[0].id, 'OFF-04')
  const why = closestExplanation(offsets)
  assert.equal(why.closest.id, 'OFF-02')
  assert.ok(why.closest.rank > 1 && why.closest.distanceKm < offsets[0].distanceKm)
  assert.deepEqual(why.weakest.map(w => w.key), ['formation', 'depth'])
  assert.equal(closestExplanation(rankedOffsets({ items: [{ well: { id: 'A' }, distance_km: 1, total_score: 0.9 }, { well: { id: 'B' }, distance_km: 2, total_score: 0.5 }] })), null)
  assert.equal(rankedOffsets({ items: [{ well: { id: 'A' }, components: { formation: 'high' } }] })[0].components.formation, null, 'non-numeric scores are unknown, never coerced')
})

test('risk levels never turn red without a backend-declared critical severity', () => {
  assert.equal(riskLevel(normalizeHazard({ type: 'stuck_pipe', probability: 0.99 })), 'high')
  assert.equal(riskLevel(normalizeHazard({ type: 'stuck_pipe', probability: 0.4 })), 'elevated')
  assert.equal(riskLevel(normalizeHazard({ type: 'stuck_pipe', probability: 0.1 })), 'low')
  assert.equal(riskLevel(normalizeHazard({ type: 'kick_or_overpressure', probability: 0.2, severity: 'critical' })), 'critical')
  assert.equal(riskLevel(normalizeHazard({ type: 'mud_loss' })), 'unknown')
  assert.equal(normalizeHazard({ type: 'x', evidence_ids: ['a', 'b'] }).evidenceCount, 2)
  assert.equal(normalizeHazard({ type: 'x' }).evidenceCount, null)
})

test('telemetry freshness and channels are never faked', () => {
  const now = Date.parse('2026-09-29T12:00:00Z')
  assert.deepEqual(freshness('2026-09-29T11:59:30Z', now), { state: 'fresh', ageS: 30 })
  assert.equal(freshness('2026-09-29T11:50:00Z', now).state, 'stale')
  assert.equal(freshness(null, now).state, 'unknown')
  const series = telemetrySeries({ channels: [{ mnemonic: 'TORQUE', unit: 'kN·m' }, { mnemonic: 'PIT', unit: 'm3' }],
    samples: [{ t: '2026-09-29T11:59:00Z', values: { TORQUE: 15, PIT: null } }, { t: '2026-09-29T11:59:30Z', values: { TORQUE: 'bad' } }] })
  assert.deepEqual(series.map(s => s.id), ['TORQUE'], 'declared channels without values are not drawn')
  assert.equal(series[0].points.length, 1)
  assert.deepEqual(telemetrySeries(null), [])
})

test('knowledge results group by well, event and report', () => {
  const groups = groupResults(adaptQuery({ results: [{ kind: 'well' }, { kind: 'event' }, { kind: 'event' }, { kind: 'mystery' }] }))
  assert.deepEqual([groups.well.length, groups.event.length, groups.report.length], [1, 2, 1])
  assert.deepEqual(listOf(null), [])
})

test('audit details hide secrets, hashes and filesystem paths', () => {
  const shown = Object.fromEntries(safeDetails({ report_id: 'DDR-1', source_path: 'C:\\data\\x.pdf', api_token: 't', content_hash: 'abc', note: '/home/oil/raw/a.pdf', count: 3 }))
  assert.deepEqual(Object.keys(shown), ['Report id', 'Note', 'Count'])
  assert.equal(shown.Note, '[path hidden]')
  assert.deepEqual(safeDetails(null), [])
})

test('development fixtures are synthetic_demo only and enforce review rules', () => {
  for (const path of ['/wells', '/wells/ACTIVE-01', '/wells/ACTIVE-01/nearby?radius_km=20', '/wells/ACTIVE-01/risk?lookahead_m=100', '/wells/ACTIVE-01/telemetry', '/wells/ACTIVE-01/correlation', '/events', '/advisories'])
    assert.ok(isSynthetic(fixtureResponse(path)), `${path} must be labelled synthetic_demo`)
  assert.ok(listOf(fixtureResponse('/events')).every(e => e.dataset_origin === 'synthetic_demo' && e.source?.report_id && e.source?.page))
  const radius2 = listOf(fixtureResponse('/wells/ACTIVE-01/nearby?radius_km=2'))
  assert.ok(radius2.length && radius2.every(o => o.distance_km <= 2))
  assert.throws(() => fixtureResponse('/advisories/ADV-0012/review', { method: 'POST', body: { decision: 'acknowledge', note: '' } }), /note/)
  assert.throws(() => fixtureResponse('/advisories/ADV-0012/review', { method: 'POST', body: { decision: 'open_valve', note: 'please do it' } }), /decision/)
  assert.throws(() => fixtureResponse('/wells/OFF-04/risk'), error => error.status === 404)
  assert.equal(fixtureResponse('/health'), undefined, 'unknown paths fall through to the real backend')
})

// P0 screens must not carry old SIH26117 refinery wording. Legacy routes live in AppPages/WorkspacePages and are excluded.
test('no MRPL / refinery / plant wording in NWIS, shell, landing or auth source', () => {
  const root = fileURLToPath(new URL('../../', import.meta.url))
  const files = []
  const walk = dir => readdirSync(dir).forEach(name => { const p = join(dir, name); if (statSync(p).isDirectory()) walk(p); else if (/\.(jsx?|css)$/.test(name) && !name.endsWith('.test.js')) files.push(p) })
  for (const dir of ['features/nwis', 'features/landing']) walk(join(root, dir))
  files.push(...['app/AppShell.jsx', 'app/navigation.js', 'app/routes.jsx', 'components/ui.jsx', 'features/auth/AuthLayout.jsx'].map(f => join(root, f)))
  const banned = /MRPL|refiner|P&(?:amp;)?ID|SCADA|\bplant\b|work order|Sovereign AI Workbench|\bstartup\b|\bshutdown\b|\bisolation\b/i
  const hits = files.flatMap(file => readFileSync(file, 'utf8').split('\n').map((line, i) => [file, i + 1, line])
    .filter(([, , line]) => banned.test(line) && !/legacy/i.test(line)))
  assert.deepEqual(hits.map(([f, n, l]) => `${f}:${n}: ${l.trim().slice(0, 100)}`), [])
})
