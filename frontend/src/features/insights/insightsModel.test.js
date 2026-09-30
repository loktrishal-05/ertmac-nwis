import test from 'node:test'
import assert from 'node:assert/strict'
import { countBy, dedupeWorkOrders, defaultSession, eventsPerDay, niceTicks, recordingSessions, sensorSeries, sumBy, workOrderBoard } from './insightsModel.js'
import { matchCommands } from '../../app/navigation.js'

const reading = (tag, iso, value, unit = 'mm/s') => ({ sensor_tag: tag, equipment_tag: 'P-204', measurement: 'vibration', unit, value, timestamp: iso, quality: 'good', citation: { source_filename: 'f.csv', source_row_number: 2 } })

test('sensor series keep physical readings only and never join separate recording sessions', () => {
  const readings = [
    reading('VIB-1', '2026-09-16T10:00:00Z', 3.1), reading('VIB-1', '2026-09-16T10:05:00Z', 8.2),
    reading('VIB-1', '2031-04-26T10:00:00Z', 3.1), reading('MARKER-1', '2026-09-16T10:00:00Z', 1, 'flag'),
    reading('VIB-2', '2026-09-16T10:00:00Z', 3.3), reading('VIB-3', 'not a date', 2),
  ]
  const series = sensorSeries(readings)
  assert.deepEqual(series.map(s => s.id), ['VIB-1', 'VIB-2'])
  const sessions = recordingSessions(series, 6 * 3600000, Date.parse('2026-09-29T00:00:00Z'))
  assert.equal(sessions.length, 2)
  assert.equal(sessions[0].future, true) // Newest first, and that one is dated in the future.
  const chosen = defaultSession(sessions)
  assert.equal(chosen.future, false)
  assert.equal(chosen.count, 3)
  assert.deepEqual(chosen.series.map(s => s.points.length), [2, 1])
})

test('axis ticks land on round numbers and cover the range', () => {
  assert.deepEqual(niceTicks(2.7, 8.6, 4), [2, 4, 6, 8, 10])
  assert.deepEqual(niceTicks(5, 5), [4, 4.5, 5, 5.5, 6])
  assert.deepEqual(niceTicks(NaN, 1), [])
})

test('work-order board follows reported statuses and keeps unknown ones visible', () => {
  const board = workOrderBoard([
    { id: 1, status: 'open', maintenance_date: '2026-06-01' }, { id: 2, status: 'closed', maintenance_date: '2026-05-01' },
    { id: 3, status: 'open', maintenance_date: '2026-07-01' }, { id: 4, status: 'deferred', maintenance_date: '2026-01-01' },
  ])
  assert.deepEqual(board.map(c => c.id), ['open', 'closed', 'deferred'])
  assert.deepEqual(board[0].items.map(o => o.id), [3, 1])
  assert.deepEqual(workOrderBoard([]).map(c => c.id), ['open', 'closed'])
})

test('repeated ingests of one work order collapse into one card with every citation', () => {
  const base = { work_order_id: 'WO-7714', equipment_tag: 'P-204', status: 'open', maintenance_date: '2026-06-01', description: 'Strainer fouling' }
  const cards = dedupeWorkOrders([{ ...base, id: 1, citation: { source_row_number: 4 } }, { ...base, id: 2, citation: { source_row_number: 9 } },
    { ...base, id: 3, equipment_tag: 'P-204A' }, { ...base, id: 4, status: 'closed' }])
  assert.equal(cards.length, 3)
  assert.equal(cards[0].ingests, 2)
  assert.deepEqual(cards[0].citations.map(c => c.source_row_number), [4, 9])
})

test('aggregations report real zeros and totals', () => {
  const days = eventsPerDay([{ occurred_at: '2026-09-21T08:00:00Z' }, { occurred_at: '2026-09-23T09:00:00Z' }, { occurred_at: '2026-09-23T10:00:00Z' }])
  assert.deepEqual(days.map(d => d.value), [1, 0, 2])
  assert.deepEqual(countBy([{ t: 'a' }, { t: 'b' }, { t: 'a' }, { t: null }], 't'), [{ label: 'a', value: 2 }, { label: 'b', value: 1 }])
  assert.deepEqual(sumBy([{ k: 'x', h: 0.5 }, { k: 'x', h: 1.25 }, { k: 'y', h: 'n/a' }], 'k', 'h'), [{ label: 'x', value: 1.75 }])
})

test('command palette ranks prefix, then substring, then initials', () => {
  const commands = [{ id: 'a', label: 'Approvals', group: 'Govern' }, { id: 'k', label: 'Knowledge Gaps', group: 'Knowledge' }, { id: 'm', label: 'Maintenance & Sensors', group: 'Evidence' }]
  assert.deepEqual(matchCommands(commands, 'appr').map(c => c.id), ['a'])
  assert.deepEqual(matchCommands(commands, 'kg').map(c => c.id), ['k'])
  assert.deepEqual(matchCommands(commands, 'sensor').map(c => c.id), ['m'])
  assert.equal(matchCommands(commands, '  ').length, 3)
  assert.equal(matchCommands(commands, 'zzz').length, 0)
})
