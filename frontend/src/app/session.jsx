import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'
import { apiRequest } from '../services/api.js'
import { LanguageContext, normalizeLanguage } from '../language.js'
import { guardDecision, sessionFromError } from './navigation.js'
import { ErrorState, Forbidden, LoadingState } from '../components/ui.jsx'

export const SessionContext = createContext({ status: 'loading', user: null, reload: () => {}, signIn: async () => {}, signOut: async () => {} })
export const useSession = () => useContext(SessionContext)

// Identity always comes from the server session cookie; nothing about the user is stored client-side.
async function fetchSession(signal) {
  try {
    return { status: 'authenticated', user: await apiRequest('/auth/me', { signal, timeout: 10000 }), error: null }
  } catch (error) {
    return sessionFromError(error)
  }
}

export function SessionProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', user: null, error: null })
  // Short-lived reset capability stays in memory, never URL/history or browser storage.
  const [recovery, setRecovery] = useState(null)
  const load = useCallback(async () => {
    const next = await fetchSession()
    setState(next)
    return next.user
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    fetchSession(controller.signal).then(next => { if (!controller.signal.aborted) setState(next) })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    const expired = () => setState({ status: 'anonymous', user: null, error: null })
    window.addEventListener('workbench-session-expired', expired)
    return () => window.removeEventListener('workbench-session-expired', expired)
  }, [])
  const signIn = useCallback(async (username, password) => {
    await apiRequest('/auth/login', { method: 'POST', body: { username, password }, timeout: 15000 })
    const user = await load()
    if (!user) throw new Error('Your session could not be confirmed. Please try signing in again.')
    return user
  }, [load])
  const signOut = useCallback(async () => {
    try {
      await apiRequest('/auth/logout', { method: 'POST' })
      setState({ status: 'anonymous', user: null, error: null })
      return true
    } catch (error) {
      setState(value => ({ ...value, error }))
      return false
    }
  }, [])
  const value = useMemo(() => ({ ...state, recovery, setRecovery, reload: load, signIn, signOut }), [state, recovery, load, signIn, signOut])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

function LanguageProvider({ children }) {
  const [language, update] = useState(() => { try { return normalizeLanguage(localStorage.getItem('workbench-language')) } catch { return 'en' } })
  useEffect(() => { document.documentElement.lang = language }, [language]) // Screen readers pick the right voice.
  const value = useMemo(() => ({ language, setLanguage: next => {
    const code = normalizeLanguage(next); update(code)
    try { localStorage.setItem('workbench-language', code) } catch { /* Session-only preference when storage is unavailable. */ }
  } }), [language])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function RootLayout() {
  return <SessionProvider><LanguageProvider><Outlet /></LanguageProvider></SessionProvider>
}

// Route guard: login redirect keeps the requested path; role failures render 403 in place.
export function RequireAuth({ roles }) {
  const session = useSession()
  const location = useLocation()
  switch (guardDecision(session, roles)) {
    case 'loading': return <LoadingState label="Checking your session…" />
    case 'unavailable': return <ErrorState title="NWIS backend unavailable" message="Your session could not be checked. No data is shown until the backend responds." onRetry={session.reload} />
    case 'login': return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
    case 'forbidden': return <Forbidden />
    default: return <Outlet />
  }
}
