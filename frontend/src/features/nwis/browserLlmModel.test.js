import test from 'node:test'
import assert from 'node:assert/strict'
import { MODELS, buildMessages, pickModels } from './browserLlmModel.js'

test('4B is primary, 2B is the fallback; low-memory devices start at 2B', () => {
  assert.deepEqual(pickModels(undefined).map(m => m.label), ['Qwen 3.5 4B', 'Qwen 3.5 2B'])
  assert.deepEqual(pickModels(8).map(m => m.label), ['Qwen 3.5 4B', 'Qwen 3.5 2B'])
  assert.deepEqual(pickModels(4), [MODELS[1]])
})

test('prompt is grounded in numbered, cited evidence only', () => {
  const items = Array.from({ length: 10 }, (_, i) => ({ event_id: `EVT-${i}`, well_id: 'OFF-04', report_id: 'OFF-04-DDR', page: 5, depth_tvd_m: 2450, excerpt: 'pipe stuck' }))
  const [system, user] = buildMessages('stuck pipe?', items)
  assert.match(system.content, /ONLY the numbered evidence/)
  assert.match(user.content, /\[1\] EVT-0 \| well OFF-04 \| report OFF-04-DDR p\.5 \| 2450 m TVD/)
  assert.match(user.content, /\[8\] EVT-7/)
  assert.doesNotMatch(user.content, /\[9\]/)
})
