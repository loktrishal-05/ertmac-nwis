import { useState } from 'react'
import { LanguageContext, normalizeLanguage, translateLabel } from './language.js'
import { LanguageSelector, ProductWorkspace } from './ProductPages.jsx'
import { OperationalWorkspace } from './OperationalPages.jsx'
import { useBackendHealth } from './hooks/useBackendHealth.js'
import { useResource } from './hooks/useApi.js'
import { Auth, Dashboard, QueryConsole, Agents, Approvals, Knowledge, Audit, Sovereignty } from './WorkspacePages.jsx'

const navigation = [
  ['Dashboard', 'grid'], ['Query Console', 'terminal'], ['Agents', 'nodes'],
  ['Approvals', 'check'], ['Knowledge Base', 'book'], ['Audit Logs', 'list'],
  ['Sovereignty', 'shield'], ['Operational Intelligence', 'tool'], ['Product Integration', 'grid'],
]

function Icon({ name, ...props }) {
  const paths = {
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    terminal: 'm5 7 5 5-5 5 M13 17h6',
    nodes: 'M9 3h6v6H9z M2 16h6v6H2z M16 16h6v6h-6z M12 9v4 M5 16v-3h14v3',
    check: 'M5 3h14v18H5z m3 9 3 3 5-6',
    book: 'M12 5v16 M3 3c4 0 6 0 9 2 3-2 5-2 9-2v16c-4 0-6 0-9 2-3-2-5-2-9-2z',
    list: 'M8 6h13 M8 12h13 M8 18h13 M3 6h1 M3 12h1 M3 18h1',
    shield: 'm12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z m-4 10 3 3 5-6',
    tool: 'm14 6 4 4 4-4c1 6-3 9-8 7l-8 8-3-3 8-8c-2-5 1-9 7-8z',
  }
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] || paths.grid} /></svg>
}

export default function App() {
  const [language, updateLanguage] = useState(() => { try { return normalizeLanguage(localStorage.getItem('workbench-language')) } catch { return 'en' } })
  const setLanguage = value => { const code = normalizeLanguage(value); updateLanguage(code); try { localStorage.setItem('workbench-language', code) } catch { /* Session-only preference when storage is unavailable. */ } }
  const t = key => translateLabel(language, key)
  const [page, setPage] = useState('Dashboard')
  const { status, checkedAt } = useBackendHealth()
  const auth = useResource('/auth/me')
  const proof = useResource('/sovereignty/proof')
  const user = auth.data
  const pages = {
    'Product Integration': <ProductWorkspace user={user} />,
    'Operational Intelligence': <OperationalWorkspace user={user} />,
    Dashboard: <Dashboard proof={proof} health={status} user={user} />,
    'Query Console': <QueryConsole user={user} />,
    Agents: <Agents />,
    Approvals: <Approvals user={user} />,
    'Knowledge Base': <Knowledge />,
    'Audit Logs': <Audit />,
    Sovereignty: <Sovereignty proof={proof} />,
  }
  return (
    <LanguageContext.Provider value={{ language, setLanguage }}><div className="workbench" lang={language}>
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Icon name="shield" /></span><div>SOVEREIGN<span>OPERATIONS WORKBENCH</span></div></div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(([name, icon]) => <button key={name} className={`nav-item ${page === name ? 'selected' : ''}`} aria-current={page === name ? 'page' : undefined} onClick={() => setPage(name)}><Icon name={icon} />{t(name)}{page === name && <span className="nav-dot" />}</button>)}
        </nav>
        <div className="sidebar-note"><Icon name="shield" /><strong>On-premise by design</strong><p>Local infrastructure.<br />Advisory recommendations only.</p><span className="sidebar-tag">SIH 2026</span></div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <LanguageSelector />
          <div className="product-name">Sovereign Agentic AI Workbench<span>INDUSTRIAL OPERATIONS</span></div>
          <div className="header-status"><span className={`connection ${status.toLowerCase()}`} role="status"><span className="status-dot" />Backend: {status}</span><span className="external-count">External AI Calls: <strong>{proof.data?.external_ai_calls ?? 'Unavailable'}</strong></span></div>
        </header>
        <main id="main" tabIndex="-1">
          <div className="page-heading"><div><h1>{t(page)}</h1><p>Your local agentic workspace, connected to the backend.</p></div><span className="phase-badge">Advisory workspace</span></div>
          <Auth auth={auth} />
          <div key={`${page}:${user?.id || 'anonymous'}:${user?.role || ''}`}>{pages[page]}</div>
          <footer><span><span className="footer-dot" />LOCAL OPERATIONS WORKBENCH</span><span>Health checked: {checkedAt ? checkedAt.toLocaleTimeString() : 'Checking...'} - Every 15s</span></footer>
        </main>
      </div>
    </div></LanguageContext.Provider>
  )
}
