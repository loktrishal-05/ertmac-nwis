import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useMatches, useNavigate } from 'react-router'
import { useSession } from './session.jsx'
import { navigationFor } from './navigation.js'
import { Icon, Logo } from '../components/ui.jsx'
import { CommandPalette } from '../features/command/CommandPalette.jsx'
import '../styles/workbench.css'
import { LanguageSelector } from '../ProductPages.jsx'
import { useBackendHealth } from '../hooks/useBackendHealth.js'
import { FIXTURE_MODE } from '../services/api.js'
import { NwisProvider } from '../features/nwis/NwisContext.jsx'
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
  const [navOpen, setNavOpen] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const main = useRef(null)
  const toggle = useRef(null)
  const menu = useRef(null)
  const title = [...matches].reverse().find(match => match.handle?.title)?.handle.title || 'eRTMAC-NWIS'
  const legacy = matches.some(match => match.handle?.legacy)

  // Route change: announce the page and move focus to its heading. Links close the drawer themselves.
  useEffect(() => {
    // Title follows what actually rendered, so a guarded route reads "Access restricted", not its own name.
    const heading = main.current?.querySelector('[data-page-title]')
    document.title = `${heading?.textContent || title} · eRTMAC-NWIS`
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
    if (await session.signOut()) navigate('/login', { replace: true })
  }

  // ⌘K / Ctrl+K opens the jump list from anywhere in the workbench.
  const [paletteOpen, setPaletteOpen] = useState(false)
  useEffect(() => {
    const onKey = event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPaletteOpen(value => !value) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const role = session.user?.role
  const commands = [
    ...navigationFor(role).flatMap(section => section.items.map(item => ({ id: item.path, label: t(item.label), group: section.group, icon: item.icon,
      run: () => navigate(`/app/${item.path}`, { viewTransition: true }) }))),
    { id: 'profile', label: 'Profile', group: 'Account', icon: 'user', run: () => navigate('/app/profile', { viewTransition: true }) },
    { id: 'theme', label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`, group: 'Action', icon: theme === 'dark' ? 'sun' : 'moon', keywords: 'appearance mode', run: toggleTheme },
    { id: 'home', label: 'Public landing page', group: 'Action', icon: 'home', run: () => navigate('/') },
    { id: 'signout', label: 'Sign out', group: 'Action', icon: 'logout', keywords: 'log out exit', run: signOut },
  ]
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return <div className="shell" data-nav-open={navOpen || undefined}>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="shell-topbar">
      <button type="button" ref={toggle} className="icon-button nav-toggle" aria-expanded={navOpen} aria-controls="shell-nav"
        aria-label={navOpen ? 'Close navigation' : 'Open navigation'} onClick={() => setNavOpen(value => !value)}>
        <Icon name={navOpen ? 'close' : 'menu'} /></button>
      <Link to="/app/dashboard" className="shell-brand" aria-label="eRTMAC-NWIS dashboard"><Logo variant="horizontal" decorative /></Link>
      <button type="button" className="search-trigger" onClick={() => setPaletteOpen(true)} aria-keyshortcuts={isMac ? 'Meta+K' : 'Control+K'}>
        <Icon name="search" size={17} /><span>Jump to…</span><kbd>{isMac ? '⌘' : 'Ctrl'} K</kbd></button>
      <div className="topbar-status">
        <span className={`pill health-${status.toLowerCase()}`} role="status"><span className="dot" aria-hidden="true" />Backend {status.toLowerCase()}</span>
        {FIXTURE_MODE && <span className="pill pill-fixture" title="Development fixtures: synthetic_demo responses served by the frontend">DEV FIXTURES</span>}
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
            {session.error && <p role="alert">Sign-out failed. {session.error.message}</p>}
          </div>
        </details>
      </div>
    </header>
    <nav id="shell-nav" className="shell-nav" aria-label="eRTMAC-NWIS">
      {navigationFor(role).map(section => <div className="nav-group" key={section.group}>
        <p className="nav-label">{section.group}</p>
        <ul>{section.items.map(item => <li key={item.path}>
          <NavLink to={`/app/${item.path}`} end={!!item.end} className="nav-link" viewTransition onClick={() => setNavOpen(false)}><Icon name={item.icon} />{t(item.label)}</NavLink>
        </li>)}</ul>
      </div>)}
      <div className="nav-note"><Icon name="shield" /><p><strong>Decision support only.</strong> NWIS advisories never operate rig equipment or change drilling parameters; engineers decide.</p></div>
    </nav>
    <button type="button" className="nav-scrim" aria-hidden="true" tabIndex={-1} onClick={() => setNavOpen(false)} />
    <main id="main" ref={main} tabIndex={-1} className="shell-main">
      {FIXTURE_MODE && <p className="shell-banner is-fixture" role="note"><strong>DEV FIXTURE MODE.</strong> NWIS data on these screens comes from frontend development fixtures (synthetic_demo), not from the NWIS backend. Production builds never include fixtures.</p>}
      {legacy && <p className="shell-banner" role="note"><strong>Legacy SIH26117 screen.</strong> Retained for regression only; not part of eRTMAC-NWIS. <Link to="/app/dashboard">Back to the NWIS dashboard</Link></p>}
      <NwisProvider><Outlet /></NwisProvider>
    </main>
    <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
  </div>
}
