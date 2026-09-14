import { useState } from 'react'
import { useBackendHealth } from './hooks/useBackendHealth.js'

const navigation = [
  ['Dashboard', 'grid'], ['Query Console', 'terminal'], ['Agents', 'nodes'],
  ['Approvals', 'check'], ['Knowledge Base', 'book'], ['Audit Logs', 'list'],
  ['Sovereignty', 'shield'],
]

const agents = [
  { name: 'Orchestrator Agent', icon: 'nodes', role: 'Workflow coordination', description: 'Coordinate domain tasks across the workbench.' },
  { name: 'Knowledge Agent', icon: 'book', role: 'Operational knowledge', description: 'Surface context from internal reference material.' },
  { name: 'Safety Agent', icon: 'shield', role: 'Process safety', description: 'Support review of operational safety considerations.' },
  { name: 'Maintenance Agent', icon: 'tool', role: 'Asset reliability', description: 'Support equipment and maintenance workflows.' },
  { name: 'Guardrail Agent', icon: 'check', role: 'Policy review', description: 'Review proposed outputs before human approval.' },
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
  const [page, setPage] = useState('Dashboard')
  const { status, checkedAt } = useBackendHealth()

  return (
    <div className="workbench">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Icon name="shield" /></span><div>SOVEREIGN<span>OPERATIONS WORKBENCH</span></div></div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(([name, icon]) => <button key={name} className={`nav-item ${page === name ? 'selected' : ''}`} aria-current={page === name ? 'page' : undefined} onClick={() => setPage(name)}><Icon name={icon} />{name}{page === name && <span className="nav-dot" />}</button>)}
        </nav>
        <div className="sidebar-note"><Icon name="shield" /><strong>On-premise by design</strong><p>Local infrastructure.<br />Your operational boundary.</p><span className="sidebar-tag">SIH 2026 · PHASE 01</span></div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="product-name">Sovereign Agentic AI Workbench<span>INDUSTRIAL OPERATIONS</span></div>
          <div className="header-status"><span className={`connection ${status.toLowerCase()}`} role="status"><span className="status-dot" />Backend: {status}</span><span className="external-count">External AI Calls: <strong>0</strong></span></div>
        </header>

        <main id="main" tabIndex="-1">
          <div className="page-heading"><div><div className="eyebrow">WORKSPACE / {page.toUpperCase()}</div><h1>{page === 'Dashboard' ? 'Operations overview' : page}</h1><p>{page === 'Dashboard' ? 'A unified view of your local agentic workspace.' : 'A reserved workspace for a future phase.'}</p></div><span className="phase-badge">Dashboard foundation</span></div>

          {page === 'Dashboard' ? <>
            <section className="metrics" aria-label="Workspace metrics">
              {[['Active Agents', 'nodes', 'No agents running'], ['Pending Approvals', 'check', 'No approval workflow'], ['Indexed Documents', 'book', 'No documents ingested'], ['External AI Calls', 'shield', 'Local-only foundation']].map(([label, icon, caption]) => <article className="metric" key={label}><div className="metric-label">{label}<Icon name={icon} /></div><div className="metric-value">0</div><p>{caption}</p></article>)}
            </section>

            <section className="agent-section" aria-labelledby="agents-title"><div className="section-heading"><div><h2 id="agents-title">Agent workspace</h2><p>Planned capabilities, ready for future implementation.</p></div><span className="count-label">05 AGENTS</span></div><div className="agent-grid">
              {agents.map((agent, index) => <article className="agent-card" key={agent.name}><div className="agent-top"><span className="agent-icon"><Icon name={agent.icon} /></span><span className="agent-number">0{index + 1}</span></div><h3>{agent.name}</h3><div className="agent-role">{agent.role}</div><p>{agent.description}</p><div className="agent-footer"><span className="not-started"><span className="status-dot" />Not Started</span><span>Planned</span></div></article>)}
            </div></section>

            <div className="lower-grid">
              <section className="panel" aria-labelledby="activity-title"><div className="section-heading"><h2 id="activity-title">Recent Activity</h2><span className="subtle-badge">PLACEHOLDERS</span></div><p className="panel-description">Preview entries only. No live audit events are recorded.</p><ul className="activity-list">{[['nodes', 'Agent execution', 'Future agent runs will appear here.'], ['check', 'Human review', 'Future approval requests will appear here.'], ['book', 'Knowledge updates', 'Future indexing activity will appear here.']].map(([icon, title, description]) => <li key={title}><span className="activity-icon"><Icon name={icon} /></span><div><strong>{title}</strong><p>{description}</p></div><span className="activity-placeholder">Pending setup</span></li>)}</ul></section>
              <section className="panel boundary-panel" aria-labelledby="boundary-title"><span className="boundary-icon"><Icon name="shield" width="26" height="26" /></span><h2 id="boundary-title">Sovereign foundation</h2><p>Built for an on-premise operational environment with local, open-weight models in future phases.</p><div className="boundary-row"><span>Hosted model integrations</span><strong>None</strong></div><div className="boundary-row"><span>Model inference</span><strong>Not configured</strong></div><div className="boundary-note">Foundation metrics are initial values, not live telemetry.</div></section>
            </div>
          </> : <section className="panel empty-state"><Icon name={navigation.find(([name]) => name === page)[1]} width="36" height="36" /><h2>{page} is not configured</h2><p>This section is reserved for a later phase. Only the dashboard foundation and backend health connection are available.</p><button className="back-button" onClick={() => setPage('Dashboard')}>Return to Dashboard</button></section>}

          <footer><span><span className="footer-dot" />PHASE 01 · FRONTEND FOUNDATION</span><span>Health checked: {checkedAt ? checkedAt.toLocaleTimeString() : 'Checking…'} · Refreshes every 15s</span></footer>
        </main>
      </div>
    </div>
  )
}
