import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { createServer } from 'vite'
import { authMediaSources, capabilitiesFrom, passwordValid, playbackMode, readMediaEnvironment, validateEmail, validateName, validateOtp } from './authModel.js'

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
  assert.deepEqual(capabilitiesFrom(null), { signup: false, email_recovery: false, admin_recovery: false, google: false })
  assert.equal(capabilitiesFrom({ signup_mode: 'disabled', google: 'yes' }).google, false)
})

test('backdrop renders poster-only fallback and a silent decorative video; sign-up stays disabled without the backend', async () => {
  const server = await vite()
  try {
    const { AuthBackdrop } = await server.ssrLoadModule('/src/features/auth/AuthLayout.jsx')
    const media = authMediaSources('login')
    const poster = renderToStaticMarkup(createElement(AuthBackdrop, { media, mode: 'poster' }))
    assert.ok(poster.includes('auth-bg-01-poster.webp') && !poster.includes('<video'))
    assert.match(poster, /aria-hidden="true"/)
    const video = renderToStaticMarkup(createElement(AuthBackdrop, { media, mode: 'video' })).toLowerCase()
    for (const attribute of ['autoplay', 'muted', 'loop', 'playsinline', 'poster="/assets/auth/auth-bg-01-poster.webp"']) assert.ok(video.includes(attribute), attribute)

    const { SignUpPage, OAuthCallbackPage } = await server.ssrLoadModule('/src/features/auth/AuthPages.jsx')
    const page = component => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(component)))
    const signup = page(SignUpPage)
    assert.match(signup, /Self-service sign-up is not enabled/)
    assert.match(signup, /<fieldset disabled=""/)
    assert.match(page(OAuthCallbackPage), /not enabled/)
  } finally { await server.close() }
})

test('landing tells the honest story without video and starts without motion', async () => {
  const server = await vite()
  try {
    const { default: LandingPage } = await server.ssrLoadModule('/src/features/landing/LandingPage.jsx')
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(LandingPage)))
    for (const id of ['hero', 'scattered', 'unify', 'workflow', 'reveal', 'pid', 'maintenance', 'governance', 'voice', 'sovereignty', 'ecosystem', 'enter']) assert.ok(html.includes(`id="${id}"`), id)
    assert.ok(!html.includes('<video'))
    assert.match(html, /not automatically air-gapped/)
    assert.equal(html.replaceAll('not tamper-proof', '').toLowerCase().includes('tamper-proof'), false)
    // Static, fully readable markup; animation is added client-side only when reduced motion is off.
    assert.match(html, /<div class="landing" data-theme="dark">/)
  } finally { await server.close() }
})
