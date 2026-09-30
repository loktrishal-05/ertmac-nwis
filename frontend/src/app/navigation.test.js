import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { createServer } from 'vite'
import { ADMINS, LEGACY_PATHS, REVIEWERS, guardDecision, navigationFor, safeNext, sessionFromError } from './navigation.js'
import { API_BASE_URL } from '../services/api.js'

const signedIn = role => ({ status: 'authenticated', user: { id: 1, username: 'u', role } })

test('guards decide from the server session, never from client state', () => {
  assert.equal(guardDecision(null), 'loading')
  assert.equal(guardDecision({ status: 'loading' }), 'loading')
  assert.equal(guardDecision({ status: 'unavailable' }), 'unavailable')
  assert.equal(guardDecision({ status: 'anonymous', user: null }), 'login')
  assert.equal(guardDecision({ status: 'authenticated', user: null }), 'login')
  assert.equal(guardDecision(signedIn('requester')), 'allow')
  assert.equal(guardDecision(signedIn('requester'), REVIEWERS), 'forbidden')
  assert.equal(guardDecision(signedIn('reviewer'), REVIEWERS), 'allow')
  assert.equal(guardDecision(signedIn('reviewer'), ADMINS), 'forbidden')
  assert.equal(guardDecision(signedIn('admin'), ADMINS), 'allow')
  assert.deepEqual(sessionFromError({ status: 401 }), { status: 'anonymous', user: null, error: null })
  assert.equal(sessionFromError({ status: 503 }).status, 'unavailable')
  assert.equal(sessionFromError(new Error('network')).status, 'unavailable')
})

test('post-login redirects stay inside the app', () => {
  assert.equal(safeNext('/app/approvals?id=1'), '/app/approvals?id=1')
  for (const next of [null, '', '/login', '/application', '/app/../login', '/app/%2e%2e/login', 'https://evil.example/app', '//evil.example/app', '/app\\..\\x', '/\\evil']) assert.equal(safeNext(next), '/app/dashboard')
})

test('navigation hides role-restricted areas and the API base defaults to the same-origin proxy', () => {
  const paths = role => navigationFor(role).flatMap(section => section.items.map(item => item.path))
  assert.ok(!paths('requester').includes('audit') && !paths('requester').includes('admin'))
  assert.ok(paths('reviewer').includes('audit') && !paths('reviewer').includes('admin'))
  assert.ok(paths('admin').includes('audit') && paths('admin').includes('admin'))
  assert.equal(API_BASE_URL, '/api')
})

test('route manifest covers every required URL with guards on restricted areas', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { routes } = await server.ssrLoadModule('/src/app/routes.jsx')
    const { RequireAuth, SessionContext } = await server.ssrLoadModule('/src/app/session.jsx')
    const found = new Map()
    const walk = (list, prefix, roles) => list.forEach(route => {
      const path = route.path ? `${prefix}/${route.path}`.replace(/\/+/g, '/') : prefix
      const guard = route.element?.type === RequireAuth ? route.element.props.roles || 'session' : roles
      if (route.path || route.index) found.set(path || '/', guard)
      if (route.children) walk(route.children, path, guard)
    })
    walk(routes, '', undefined)
    // eRTMAC-NWIS routes (master report §16) plus legacy SIH26117 routes kept routable but hidden from navigation.
    for (const path of ['/', '/login', '/signup', '/forgot-password', '/verify-otp', '/reset-password', '/auth/callback', '/app/dashboard',
      '/app/wells', '/app/map', '/app/wells/:id', '/app/active', '/app/offset-analysis', '/app/correlation', '/app/events', '/app/risk', '/app/live',
      '/app/knowledge', '/app/advisories', '/app/audit', '/app/help',
      '/app/workspace', '/app/workspace/voice', '/app/agents', '/app/pid', '/app/maintenance', '/app/operations/:view',
      '/app/gaps', '/app/approvals', '/app/executions', '/app/sovereignty', '/app/resources', '/app/admin', '/app/admin/*',
      '/app/profile', '/403', '/*']) assert.ok(found.has(path), `missing route ${path}`)
    const navPaths = navigationFor('admin').flatMap(section => section.items.map(item => item.path))
    for (const path of LEGACY_PATHS) assert.ok(!navPaths.includes(path), `legacy route ${path} must not be in primary navigation`)
    assert.equal(found.get('/app/dashboard'), 'session')
    assert.deepEqual(found.get('/app/audit'), REVIEWERS)
    assert.deepEqual(found.get('/app/admin/*'), ADMINS)
    assert.equal(found.get('/login'), undefined)

    const guard = (session, roles) => renderToStaticMarkup(createElement(MemoryRouter, null,
      createElement(SessionContext.Provider, { value: { reload() {}, ...session } }, createElement(RequireAuth, { roles }))))
    assert.match(guard({ status: 'loading' }), /Checking your session/)
    assert.match(guard({ status: 'unavailable' }), /backend unavailable/)
    assert.match(guard(signedIn('requester'), ADMINS), /403|restricted/i)
  } finally { await server.close() }
})
