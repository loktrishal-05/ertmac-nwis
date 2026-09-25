import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('operational Workspace requires login and preserves advisory trust labels', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { OperationalWorkspace } = await server.ssrLoadModule('/src/OperationalPages.jsx')
    const anon = renderToStaticMarkup(createElement(OperationalWorkspace, {}))
    assert.match(anon, /Sign in/)
    assert.ok(!anon.includes('<form'))
    const html = renderToStaticMarkup(createElement(OperationalWorkspace, { user: { role: 'requester' } }))
    for (const label of ['Shift Handover', 'Environmental Compliance', 'Operator Notes', 'Knowledge Gaps', 'human-reported', '72 hours', 'never authorizes']) assert.ok(html.includes(label))
    assert.ok(!html.includes('Execute plant'))
  } finally { await server.close() }
})
