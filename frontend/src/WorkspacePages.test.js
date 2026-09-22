import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('backend result and availability states render without invented authority', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { Result, ApiState } = await server.ssrLoadModule('/src/WorkspacePages.jsx')
    const render = (component, props) => renderToStaticMarkup(createElement(component, props))
    for (const status of ['refused', 'clarification_required', 'insufficient_evidence']) {
      const html = render(Result, { data: { governance_status: 'INFORMATIONAL', agent_result: { schema: 'S5', output: { status, reason: 'Backend reason' } } } })
      assert.ok(html.includes(`<p class="review-notice">${status.replaceAll('_', ' ')}</p>`))
      assert.ok(html.includes('Backend reason'))
    }
    const draft = render(Result, { data: { governance_status: 'PENDING_REVIEW', route: 'maintenance', action_revision_id: 'revision-a', evidence: [{ evidence_id: 'source-a', locator: 'page 2', quote: '<script>unsafe</script>' }] } })
    assert.match(draft, /Human approval required/)
    assert.match(draft, /revision-a/)
    assert.match(draft, /page 2/)
    assert.ok(!draft.includes('<script>'))
    assert.ok(!render(Result, { data: { governance_status: 'REVOKED' } }).includes('Human approval required'))
    assert.match(render(ApiState, { request: { loading: true } }), /role="status"/)
    for (const data of [[], {}]) assert.match(render(ApiState, { request: { data } }), /No records returned/)
    assert.match(render(ApiState, { request: { error: { status: 401 } } }), /Sign in/)
    assert.match(render(ApiState, { request: { error: { status: 403, message: 'Server denied' } } }), /Access denied: Server denied/)
  } finally {
    await server.close()
  }
})
