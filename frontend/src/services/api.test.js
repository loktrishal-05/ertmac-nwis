import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { FIXTURE_MODE, apiRequest, getBackendHealth } from './api.js'

test('requests use server cookies and preserve exact revision binding', async (t) => {
  let seen
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    seen = { url, ...options }
    return new Response(JSON.stringify({ decision: 'APPROVE' }))
  })
  const body = { decision: 'approve', expected_revision_id: 'exact-revision' }
  await apiRequest('/approvals/exact-revision/decision', { method: 'POST', body })
  assert.equal(seen.credentials, 'include')
  assert.equal(seen.cache, 'no-store')
  assert.deepEqual(JSON.parse(seen.body), body)
  assert.equal(seen.headers.Authorization, undefined)
})

test('backend authorization errors and readiness details survive', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: 'Self-approval is prohibited' }), { status: 403 }))
  await assert.rejects(apiRequest('/approvals/revision/decision'), error => error.status === 403 && error.message.includes('Self-approval'))
})

test('non-JSON errors do not crash parsing or produce fake success', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('unavailable', { status: 503 }))
  await assert.rejects(apiRequest('/ready'), error => error.status === 503)
})

test('auth validation shows safe field messages without serializing the response', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: [{ msg: 'Enter a valid email address', loc: ['body', 'email'], type: 'value_error' }] }), { status: 422 }))
  await assert.rejects(apiRequest('/auth/signup'), error => error.message === 'Enter a valid email address' && error.status === 422)
})

test('empty successful response is rejected', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(''))
  await assert.rejects(apiRequest('/query'), /empty or invalid JSON/)
})

test('health requires HTTP success and a healthy status, not a specific service brand', async (t) => {
  for (const service of ['sovereign-agentic-workbench-backend', 'ertmac-nwis-backend', undefined]) {
    t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ status: 'ok', service })))
    assert.equal((await getBackendHealth()).status, 'ok')
  }
  for (const body of [{ status: 'degraded' }, { service: 'ertmac-nwis-backend' }, { status: 'error' }]) {
    t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(body)))
    await assert.rejects(getBackendHealth(), /Unexpected backend/)
  }
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ status: 'ok' }), { status: 503 }))
  await assert.rejects(getBackendHealth(), error => error.status === 503)
})

test('NWIS fixtures are gated on DEV + VITE_NWIS_FIXTURES and never used as a failure fallback', async (t) => {
  const source = readFileSync(new URL('./api.js', import.meta.url), 'utf8')
  assert.match(source, /FIXTURE_MODE = !!\(import\.meta\.env\?\.DEV && import\.meta\.env\?\.VITE_NWIS_FIXTURES === '1'\)/)
  assert.equal(source.match(/features\/nwis\/fixtures\.js/g)?.length, 1, 'exactly one fixture import, inside the FIXTURE_MODE branch')
  assert.ok(source.indexOf("import('../features/nwis/fixtures.js')") > source.indexOf('if (FIXTURE_MODE) {'), 'fixture import only inside the gate')
  assert.ok(!/catch[^}]*fixture/i.test(source), 'no fixture fallback in error handling')
  assert.equal(FIXTURE_MODE, false, 'outside Vite dev (tests, production) fixtures are off')
  // A failing NWIS endpoint surfaces the error; nothing is substituted.
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: 'NWIS unavailable' }), { status: 503 }))
  await assert.rejects(apiRequest('/wells/ACTIVE-01/risk?lookahead_m=100'), error => error.status === 503 && /NWIS unavailable/.test(error.message))
})

test('timeouts surface uncertainty and do not retry submissions', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', (_url, { signal }) => new Promise((_resolve, reject) => {
    calls += 1
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  }))
  await assert.rejects(apiRequest('/query', { method: 'POST', body: { query: 'question' }, timeout: 5 }), /Check current backend state/)
  assert.equal(calls, 1)
})
