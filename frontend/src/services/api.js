const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

export async function apiRequest(path, { signal, method = 'GET', body, timeout = 30000 } = {}) {
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
      const message = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `Request failed (${response.status})`
      const error = new Error(message)
      error.status = response.status
      error.data = data
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

export async function getBackendHealth(signal) {
  const health = await apiRequest('/health', { signal, timeout: 5000 })
  if (health.status !== 'ok' || health.service !== 'sovereign-agentic-workbench-backend') {
    throw new Error('Unexpected backend health response')
  }
  return health
}
