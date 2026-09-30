import test from 'node:test'
import assert from 'node:assert/strict'
import { rewriteApiPath } from './apiRoutes.js'

test('dev proxy keeps /api for NWIS routes and strips it for root backend routes', () => {
  for (const path of ['/api/wells?limit=100', '/api/wells/ACTIVE-01/risk?lookahead_m=100', '/api/events', '/api/query', '/api/assessments/abc', '/api/advisories/ADV-1/review',
    '/api/terms/accept', '/api/reports/OFF-04-DDR/source', '/api/audit', '/api/audit?limit=100']) assert.equal(rewriteApiPath(path), path)
  assert.equal(rewriteApiPath('/api/auth/me'), '/auth/me')
  assert.equal(rewriteApiPath('/api/health'), '/health')
  assert.equal(rewriteApiPath('/api/audit/verify'), '/audit/verify')
  assert.equal(rewriteApiPath('/api/wellsx'), '/wellsx', 'prefix match is on whole path segments')
  assert.equal(rewriteApiPath('/api'), '/')
})
