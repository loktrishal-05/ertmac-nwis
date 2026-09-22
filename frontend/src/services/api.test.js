import test from 'node:test'
import assert from 'node:assert/strict'
import { apiRequest, getBackendHealth } from './api.js'

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

test('empty successful response is rejected', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(''))
  await assert.rejects(apiRequest('/query'), /empty or invalid JSON/)
})

test('health validates the actual service contract', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ status: 'ok', service: 'other' })))
  await assert.rejects(getBackendHealth(), /Unexpected backend/)
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
