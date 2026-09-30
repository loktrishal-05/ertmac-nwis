import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { normalizeLanguage, translateLabel } from './language.js'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { createHmac, randomUUID } from 'node:crypto'

test('language selection switches curated labels and preserves technical identifiers', () => {
  for (const code of ['en', 'hi', 'ta']) assert.equal(normalizeLanguage(code), code)
  assert.equal(normalizeLanguage('unsupported'), 'en')
  assert.notEqual(translateLabel('en', 'Question'), translateLabel('hi', 'Question'))
  assert.notEqual(translateLabel('hi', 'Question'), translateLabel('ta', 'Question'))
  for (const code of ['en', 'hi', 'ta']) {
    for (const id of ['P-204A', 'XV-2040', 'SOP-P204-001', 'document-123']) assert.equal(translateLabel(code, id), id)
  }
})

test('n8n template signs only summary requests and rejects public destinations', () => {
  const workflow = JSON.parse(readFileSync(new URL('../../infra/n8n/05-wb-operational-summary.json', import.meta.url)))
  const code = workflow.nodes[1].parameters.jsCode
  const execute = base => runInNewContext(`(function(){${code}})()`, { URL,
    require: () => ({ createHmac, randomUUID }), $env: { WORKBENCH_BASE_URL: base, WORKBENCH_AUTOMATION_SECRET: 'test-only-'.repeat(4) } })[0].json
  const result = execute('http://127.0.0.1:8000')
  assert.equal(result.kind, 'audit_summary')
  assert.equal(result.signature, createHmac('sha256', 'test-only-'.repeat(4)).update(`${result.timestamp}.${result.nonce}.${result.kind}`).digest('hex'))
  for (const url of ['https://public.example.com', 'http://localhost.evil.example', 'http://127.0.0.1.evil.example', 'http://user:secret@localhost']) assert.throws(() => execute(url))
  assert.equal(workflow.active, false)
  assert.ok(workflow.nodes[2].parameters.url.endsWith("'/automation/webhook' }}"))
})

test('voice, BI, automation and language views expose availability without authority', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const views = await server.ssrLoadModule('/src/ProductPages.jsx')
    const { LanguageContext } = await server.ssrLoadModule('/src/language.js')
    const render = (Component, props, language = 'en') => renderToStaticMarkup(createElement(LanguageContext.Provider,
      { value: { language, setLanguage: () => {} } }, createElement(Component, props)))
    assert.match(render(views.VoiceAvailability, {}), /Voice unavailable; text mode remains available/)
    assert.match(render(views.VoiceControls, {}), /disabled/)
    assert.match(render(views.ProductWorkspace, {}), /Sign in/)
    const sample = { sampled_runs: 2, metadata_runs: 1, sample_limit: 1000,
      metrics: { open_incidents: null, pending_human_approvals: 3 }, evidence_sufficiency: { PARTIAL: 1 }, execution_paths: { MGS_PATH: 1 } }
    const bi = render(views.BIReport, { data: sample })
    for (const text of ['Unavailable', 'pending human approvals', 'PARTIAL', 'MGS PATH', 'No permission']) assert.ok(bi.includes(text), text)
    assert.match(render(views.AutomationStatus, { data: { automation: 'disabled', automation_authority: 'summary_only' } }), /summary_only/)
    for (const code of ['hi', 'ta']) {
      assert.ok(render(views.LanguageSelector, {}, code).includes(`value="${code}" selected`))
      assert.ok(render(views.BIReport, { data: sample }, code).includes(translateLabel(code, 'Operational BI')))
    }
    const { DataView } = await server.ssrLoadModule('/src/WorkspacePages.jsx')
    // Original-language evidence text stays exact; identifiers are wrapped only to keep them on one line.
    const evidence = render(DataView, { value: 'P-204A XV-2040 मूल उद्धरण' }, 'ta')
    assert.equal(evidence.replace(/<[^>]+>/g, ''), 'P-204A XV-2040 मूल उद्धरण')
    assert.match(evidence, /<span class="identifier">P-204A<\/span> <span class="identifier">XV-2040<\/span>/)
  } finally { await server.close() }
})
