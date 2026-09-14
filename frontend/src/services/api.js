const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

export async function getBackendHealth(signal) {
  const response = await fetch(`${API_BASE_URL}/health`, {
    signal,
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })

  if (!response.ok) throw new Error(`Health request failed (${response.status})`)

  const health = await response.json()
  if (health.status !== 'ok' || health.service !== 'sovereign-agentic-workbench-backend') {
    throw new Error('Unexpected backend health response')
  }
  return health
}
