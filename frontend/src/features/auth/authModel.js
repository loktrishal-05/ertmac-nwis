// Auth media and validation rules. Pure; mirrored server-side when the account API lands.

// Only the three approved videos, and only on authentication routes.
const MEDIA = { login: ['01', 'center'], signup: ['03', 'upper'], recovery: ['02', 'center'] }

export function authMediaSources(group, narrow = false) {
  const [id, placement] = MEDIA[group] || MEDIA.login
  const base = `/assets/auth/auth-bg-${id}`
  return { id, placement, video: `${base}${narrow ? '-mobile' : ''}.mp4`, poster: `${base}-poster.webp` }
}

// Poster-only whenever motion or data should be spared. Unknown environments stay on the poster.
export function playbackMode(env) {
  if (!env || env.reducedMotion || env.saveData) return 'poster'
  if (['slow-2g', '2g', '3g'].includes(env.effectiveType)) return 'poster'
  return 'video'
}

export function readMediaEnvironment(win = globalThis.window) {
  if (!win?.matchMedia) return null
  const connection = win.navigator?.connection
  return {
    reducedMotion: win.matchMedia('(prefers-reduced-motion: reduce)').matches,
    saveData: !!connection?.saveData,
    effectiveType: connection?.effectiveType,
    narrow: win.matchMedia('(max-width: 760px)').matches,
  }
}

export function validateName(value) {
  const name = (value || '').trim()
  if (name.length < 2 || name.length > 100) return 'Enter your name (2 to 100 characters).'
  if (!/\p{L}/u.test(name)) return 'A name must contain letters. Digits-only names are not accepted.'
  if (!/^\p{L}[\p{L}\p{M} .'’-]*$/u.test(name)) return 'Use letters, spaces, apostrophes, hyphens or full stops only.'
  return null
}

export const normalizeEmail = value => (value || '').trim().toLowerCase()

export function validateEmail(value) {
  const email = normalizeEmail(value)
  if (email.length > 254 || email.includes('..') || !/^[^\s@]{1,64}@[^\s@.][^\s@]*\.[^\s@.]{2,}$/.test(email)) return 'Enter a valid email address.'
  return null
}

// A short sample only; the server checks a full common-password list.
const COMMON = new Set(['password', 'password123', 'password1234', '123456789012', 'qwertyuiopas', 'administrator', 'welcome12345', 'letmein12345', 'iloveyou1234', 'sovereign123'])

export function passwordChecks(password = '', { email = '', name = '' } = {}) {
  const lower = password.toLowerCase()
  const personal = [normalizeEmail(email).split('@')[0], ...name.toLowerCase().split(/\s+/)].filter(part => part.length >= 3)
  return [
    { id: 'length', label: 'At least 12 characters', ok: [...password].length >= 12 },
    { id: 'max', label: 'No more than 128 characters', ok: [...password].length <= 128 },
    { id: 'common', label: 'Not a commonly used password', ok: !!password && !COMMON.has(lower) },
    { id: 'personal', label: 'Does not contain your name or email', ok: !!password && !personal.some(part => lower.includes(part)) },
  ]
}

export const passwordValid = (password, context) => passwordChecks(password, context).every(check => check.ok)
export const validateOtp = code => (/^\d{6}$/.test(code || '') ? null : 'Enter the 6-digit code.')

// Until the backend reports a capability, every self-service flow stays off. Never pretend.
export const NO_CAPABILITIES = { signup: false, email_recovery: false, admin_recovery: false, google: false }
export function capabilitiesFrom(data) {
  if (!data || typeof data !== 'object') return NO_CAPABILITIES
  return { signup: data.signup_mode === 'open' || data.signup_mode === 'approval', signup_mode: data.signup_mode,
    email_recovery: data.email_recovery === true, admin_recovery: data.admin_recovery === true, google: data.google === true }
}
