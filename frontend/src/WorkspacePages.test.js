import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('backend result and availability states render without invented authority', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { Result, ApiState, ExecutionPanel } = await server.ssrLoadModule('/src/WorkspacePages.jsx')
    const render = (component, props) => renderToStaticMarkup(createElement(component, props))
    assert.equal(render(ExecutionPanel, {}), '')
    const execution = render(ExecutionPanel, { execution: { execution_path: 'MGS_PATH',
      evidence_sufficiency: { state: 'PARTIAL', missing_categories: ['maintenance'] },
      retrieved_sources: 2, model_used: ['local-model'], total_latency_ms: 1250, fallback_used: true,
      hidden_reasoning: 'DO NOT DISPLAY PRIVATE TRACE' } })
    for (const text of ['MGS', 'PARTIAL', 'maintenance', 'local-model', '1.25 s', 'Safe fallback', 'not permission']) assert.ok(execution.includes(text))
    assert.ok(!execution.includes('PRIVATE TRACE'))
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
    const advisory = render(Result, { data: { governance_status: 'PENDING_REVIEW',
      agent_result: { schema: 'S7', output: { observations: ['Recorded vibration increased'],
        hypotheses: [{ text: 'Possible cause; unconfirmed' }], limitations: ['Historical synthetic data'] } },
      evidence: [{ kind: 'pid_region', evidence_id: 'drawing', locator: 'R3 page 1' }] } })
    for (const text of ['observations', 'hypotheses', 'limitations', 'as drawn only', 'Historical synthetic data']) assert.ok(advisory.includes(text))
    assert.ok(!render(Result, { data: { governance_status: 'REVOKED' } }).includes('Human approval required'))
    assert.match(render(ApiState, { request: { loading: true } }), /role="status"/)
    for (const data of [[], {}]) assert.match(render(ApiState, { request: { data } }), /No records returned/)
    assert.match(render(ApiState, { request: { error: { status: 401 } } }), /Sign in/)
    assert.match(render(ApiState, { request: { error: { status: 403, message: 'Server denied' } } }), /Access denied: Server denied/)
  } finally {
    await server.close()
  }
})
