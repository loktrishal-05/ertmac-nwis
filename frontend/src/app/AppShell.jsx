import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useMatches, useNavigate } from 'react-router'
import { useSession } from './session.jsx'
import { navigationFor } from './navigation.js'
import { Icon, Logo } from '../components/ui.jsx'
import { LanguageSelector } from '../ProductPages.jsx'
import { useBackendHealth } from '../hooks/useBackendHealth.js'
import { useResource } from '../hooks/useApi.js'
import { useLanguage } from '../language.js'

const THEME_KEY = 'workbench-theme'
function useTheme() {
  // The workbench is calm and light by default; dark stays available for control rooms.
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light' } catch { return 'light' } })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem(THEME_KEY, theme) } catch { /* Preference is optional. */ }
  }, [theme])
  return [theme, () => setTheme(value => value === 'dark' ? 'light' : 'dark')]
}

export default function AppShell() {
  const session = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const matches = useMatches()
  const { t } = useLanguage()
  const { status } = useBackendHealth()
  const proof = useResource('/sovereignty/proof')
  const [navOpen, setNavOpen] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const main = useRef(null)
  const toggle = useRef(null)
  const menu = useRef(null)
  const title = [...matches].reverse().find(match => match.handle?.title)?.handle.title || 'Workbench'

  // Route change: announce the page and move focus to its heading. Links close the drawer themselves.
  useEffect(() => {
    // Title follows what actually rendered, so a guarded route reads "Access restricted", not its own name.
    const heading = main.current?.querySelector('[data-page-title]')
    document.title = `${heading?.textContent || title} · Sovereign AI Workbench`
    ;(heading || main.current)?.focus({ preventScroll: true })
    if (menu.current) menu.current.open = false
  }, [location.pathname, title])
  // The account menu is a <details>: close it on Escape (returning focus) and on any outside press.
  useEffect(() => {
    const close = event => {
      const el = menu.current
      if (!el?.open) return
      if (event.type === 'keydown' ? event.key === 'Escape' : !el.contains(event.target)) {
        el.open = false
        if (event.type === 'keydown') el.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => { document.removeEventListener('keydown', close); document.removeEventListener('pointerdown', close) }
  }, [])
  useEffect(() => {
    if (!navOpen) return undefined
    const onKey = event => { if (event.key === 'Escape') { setNavOpen(false); toggle.current?.focus() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])

  async function signOut() {
    await session.signOut()
    navigate('/login', { replace: true })
  }

  const role = session.user?.role
  return <div className="shell" data-nav-open={navOpen || undefined}>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="shell-topbar">
      <button type="button" ref={toggle} className="icon-button nav-toggle" aria-expanded={navOpen} aria-controls="shell-nav"
        aria-label={navOpen ? 'Close navigation' : 'Open navigation'} onClick={() => setNavOpen(value => !value)}>
        <Icon name={navOpen ? 'close' : 'menu'} /></button>
      <Link to="/app/dashboard" className="shell-brand" aria-label="Sovereign AI Workbench dashboard"><Logo variant="horizontal" decorative /></Link>
      <div className="topbar-status">
        <span className={`pill health-${status.toLowerCase()}`} role="status"><span className="dot" aria-hidden="true" />Backend: {status}</span>
        <span className="pill" title="Hosted AI calls observed by this backend process">Hosted AI calls: <strong>{proof.data?.external_ai_calls ?? '—'}</strong></span>
      </div>
      <div className="topbar-actions">
        <LanguageSelector />
        <button type="button" className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} /></button>
        <details className="user-menu" ref={menu}>
          <summary aria-label="Account menu"><Icon name="user" /><span className="user-name">{session.user?.username}</span></summary>
          <div className="menu-panel">
            <p><strong>{session.user?.username}</strong><br /><span className="muted">Server role: {role}</span></p>
            <Link to="/app/profile">Profile</Link>
            <button type="button" onClick={signOut}>Sign out</button>
          </div>
        </details>
      </div>
    </header>
    <nav id="shell-nav" className="shell-nav" aria-label="Workbench">
      {navigationFor(role).map(section => <div className="nav-group" key={section.group}>
        <p className="nav-label">{section.group}</p>
        <ul>{section.items.map(item => <li key={item.path}>
          <NavLink to={`/app/${item.path}`} end={item.path === 'workspace'} className="nav-link" onClick={() => setNavOpen(false)}><Icon name={item.icon} />{t(item.label)}</NavLink>
        </li>)}</ul>
      </div>)}
      <div className="nav-note"><Icon name="shield" /><p><strong>On-premise by design.</strong> Local inference; recommendations are advisory and never operate equipment.</p></div>
    </nav>
    <button type="button" className="nav-scrim" aria-hidden="true" tabIndex={-1} onClick={() => setNavOpen(false)} />
    <main id="main" ref={main} tabIndex={-1} className="shell-main"><Outlet /></main>
  </div>
}
