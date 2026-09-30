import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { createServer } from 'vite'
import { readFileSync } from 'node:fs'
import { authMediaSources, capabilitiesFrom, passwordValid, playbackMode, readMediaEnvironment, recoveryIdentifier, validateEmail, validateName, validateOtp } from './authModel.js'

const vite = () => createServer({ configFile: false, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })

test('auth video plays only when motion and data allow, otherwise the poster stays', () => {
  const fast = { reducedMotion: false, saveData: false, effectiveType: '4g' }
  assert.equal(playbackMode(fast), 'video')
  assert.equal(playbackMode(null), 'poster')
  assert.equal(playbackMode({ ...fast, reducedMotion: true }), 'poster')
  assert.equal(playbackMode({ ...fast, saveData: true }), 'poster')
  for (const effectiveType of ['slow-2g', '2g', '3g']) assert.equal(playbackMode({ ...fast, effectiveType }), 'poster')
  assert.equal(readMediaEnvironment(undefined), null)
  const env = readMediaEnvironment({ matchMedia: query => ({ matches: query.includes('reduce') }), navigator: { connection: { saveData: true, effectiveType: '4g' } } })
  assert.deepEqual(env, { reducedMotion: true, saveData: true, effectiveType: '4g', narrow: false })
})

test('each auth route family uses its approved video and placement', () => {
  assert.deepEqual(authMediaSources('login'), { id: '01', placement: 'center', video: '/assets/auth/auth-bg-01.mp4', poster: '/assets/auth/auth-bg-01-poster.webp' })
  assert.equal(authMediaSources('signup').id, '03')
  assert.equal(authMediaSources('signup').placement, 'upper')
  assert.equal(authMediaSources('recovery', true).video, '/assets/auth/auth-bg-02-mobile.mp4')
  assert.equal(authMediaSources('unknown').id, '01')
})

test('account form validation and capability defaults are honest', () => {
  for (const name of ['Priya Nair', 'प्रिया', 'பிரியா', "O'Neil-Smith"]) assert.equal(validateName(name), null, name)
  for (const name of ['', 'A', '12345', '-Priya', 'Priya<script>']) assert.notEqual(validateName(name), null, name)
  assert.equal(validateEmail(' Priya@Plant.example.in '), null)
  for (const email of ['priya', 'priya@plant', 'a..b@plant.in', 'a b@plant.in']) assert.notEqual(validateEmail(email), null)
  assert.equal(passwordValid('turbine-lantern-47', { email: 'priya@plant.in', name: 'Priya Nair' }), true)
  assert.equal(passwordValid('short', {}), false)
  assert.equal(passwordValid('password1234', {}), false)
  assert.equal(passwordValid('priya-turbine-47', { email: 'priya@plant.in' }), false)
  assert.equal(validateOtp('123456'), null)
  assert.notEqual(validateOtp('12345a'), null)
  assert.deepEqual(capabilitiesFrom(null), { signup: false, email_recovery: false, email_delivery: 'none', admin_recovery: false, google: false })
  assert.equal(capabilitiesFrom({ email_delivery: 'local' }).email_delivery, 'local')
  assert.equal(capabilitiesFrom({ email_delivery: 'carrier-pigeon' }).email_delivery, 'none')
  assert.equal(capabilitiesFrom({ signup_mode: 'disabled', google: 'yes' }).google, false)
  assert.equal(capabilitiesFrom({ signup: false, signup_mode: 'open' }).signup, false)
  assert.equal(capabilitiesFrom({ signup: true, signup_mode: 'approval' }).signup, true)
  assert.deepEqual(recoveryIdentifier(' Alice@Example.com '), { email: 'alice@example.com' })
  assert.deepEqual(recoveryIdentifier(' legacy_user '), { username: 'legacy_user' })
})

test('auth backdrop is a decorative subsurface canvas (no footage); sign-up stays disabled without the backend', async () => {
  const server = await vite()
  try {
    const { default: SubsurfaceCanvas } = await server.ssrLoadModule('/src/features/landing/SubsurfaceCanvas.jsx')
    const scene = renderToStaticMarkup(createElement(SubsurfaceCanvas, { className: 'auth-scene' }))
    assert.match(scene, /<canvas class="auth-scene" aria-hidden="true">/)
    const layout = readFileSync(new URL('./AuthLayout.jsx', import.meta.url), 'utf8')
    assert.ok(!layout.includes('<video') && !layout.includes('/assets/auth/'), 'auth no longer ships the old footage')
    assert.match(layout, /Pause background animation/)

    const { SignUpPage, OAuthCallbackPage } = await server.ssrLoadModule('/src/features/auth/AuthPages.jsx')
    const page = component => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component)))
    const signup = page(SignUpPage)
    assert.match(signup, /Self-service sign-up is not enabled/)
    assert.match(signup, /<fieldset disabled=""/)
    assert.match(page(OAuthCallbackPage), /not enabled/)
  } finally { await server.close() }
})

test('landing tells the honest NWIS story without video and starts without motion', async () => {
  const server = await vite()
  try {
    const { default: LandingPage } = await server.ssrLoadModule('/src/features/landing/LandingPage.jsx')
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(LandingPage)))
    for (const id of ['hero', 'reports', 'nearby', 'correlation', 'telemetry', 'lookahead', 'evidence', 'architecture', 'enter']) assert.ok(html.includes(`id="${id}"`), id)
    assert.ok(!html.includes('<video'))
    assert.match(html, /eRTMAC sees the live well/)
    assert.ok(html.includes("Designed for Oil India / eRTMAC workflows"))
    assert.equal(html.replaceAll('not deployed at Oil India', '').includes('deployed at Oil India'), false, 'never claims deployment')
    assert.match(html, /synthetic/i)
    assert.equal(html.replaceAll('not tamper-proof', '').toLowerCase().includes('tamper-proof'), false)
    // Static, fully readable markup; animation is added client-side only when reduced motion is off.
    assert.match(html, /<div class="landing" data-theme="dark">/)
  } finally { await server.close() }
})
