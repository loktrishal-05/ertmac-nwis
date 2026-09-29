// Same-origin by default (Vite proxy in development, site reverse proxy in production).
export const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

// Development-only NWIS fixtures (synthetic_demo). Both conditions are required, and Vite folds `DEV` to false in
// production builds, so the fixture module is never bundled or reachable there. The shell shows a banner when on.
export const FIXTURE_MODE = !!(import.meta.env?.DEV && import.meta.env?.VITE_NWIS_FIXTURES === '1')

export async function apiRequest(path, { signal, method = 'GET', body, timeout = 30000 } = {}) {
  if (FIXTURE_MODE) {
    const { fixtureResponse } = await import('../features/nwis/fixtures.js')
    const data = fixtureResponse(path, { method, body })
    if (data !== undefined) return structuredClone(data)
  }
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  const timer = setTimeout(abort, timeout)
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method, signal: controller.signal, credentials: 'include', cache: 'no-store',
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = data?.detail
      const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg).join(' ') : `Request failed (${response.status})`
      const error = new Error(message)
      error.status = response.status
      error.data = data
      if (response.status === 401 && !['/auth/login', '/auth/me'].includes(path)) globalThis.window?.dispatchEvent(new Event('workbench-session-expired'))
      throw error
    }
    if (data === null) throw new Error('Backend returned an empty or invalid JSON response.')
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Request cancelled or timed out. Check current backend state before retrying a submission.')
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

const HEALTHY_STATUS = new Set(['ok', 'healthy', 'up'])

export async function getBackendHealth(signal) {
  const health = await apiRequest('/health', { signal, timeout: 5000 })
  // Healthy = HTTP success + a healthy status field. The service name is not checked, so a rebrand to eRTMAC-NWIS is safe.
  if (!HEALTHY_STATUS.has(String(health?.status ?? '').toLowerCase())) {
    throw new Error('Unexpected backend health response')
  }
  return health
}
