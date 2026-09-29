import { useEffect } from 'react'
import { Link, isRouteErrorResponse, useRouteError } from 'react-router'

const ICONS = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  terminal: 'M3 4h18v16H3z m3 5 3 3-3 3 m5 0h6',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z M5 11a7 7 0 0 0 14 0 M12 18v3',
  agent: 'M7 8h10a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3z M12 4v4 M9 13h.01 M15 13h.01',
  drawing: 'M3 5h18v14H3z M7 9h4v4H7z M11 11h6 M17 9v6',
  pulse: 'M3 12h4l2-6 4 12 2-6h6',
  tool: 'm14 6 4 4 4-4c1 6-3 9-8 7l-8 8-3-3 8-8c-2-5 1-9 7-8z',
  book: 'M12 5v16 M3 3c4 0 6 0 9 2 3-2 5-2 9-2v16c-4 0-6 0-9 2-3-2-5-2-9-2z',
  gap: 'M4 4h6v6H4z M14 14h6v6h-6z M10 7h4v4 M7 10v4h4',
  check: 'M5 3h14v18H5z m3 9 3 3 5-6',
  timeline: 'M4 6h16 M4 12h10 M4 18h13 M8 4v4 M18 16v4 M12 10v4',
  list: 'M8 6h13 M8 12h13 M8 18h13 M3 6h1 M3 12h1 M3 18h1',
  shield: 'm12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z m-4 10 3 3 5-6',
  globe: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18',
  users: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M2 21c0-4 3-6 7-6s7 2 7 6 M16 3a4 4 0 0 1 0 8 M22 21c0-3-2-5-4-6',
  menu: 'M4 7h16 M4 12h16 M4 17h16',
  close: 'M6 6l12 12 M18 6 6 18',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21c0-4 4-6 8-6s8 2 8 6',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 2v2 M12 20v2 M4 12H2 M22 12h-2 M5 5l1.5 1.5 M17.5 17.5 19 19 M5 19l1.5-1.5 M17.5 6.5 19 5',
  moon: 'M20 14A8 8 0 0 1 10 4a8 8 0 1 0 10 10z',
  pause: 'M8 5h3v14H8z M13 5h3v14h-3z',
  play: 'M7 5l12 7-12 7z',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  alert: 'M12 3 2 21h20z M12 10v5 M12 18h.01',
  lock: 'M6 11h12v10H6z M8 11V8a4 4 0 0 1 8 0v3',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z m9 16-4.35-4.35',
  home: 'M3 11 12 4l9 7 M5 10v10h14V10',
  logout: 'M15 4h4v16h-4 M10 8l-4 4 4 4 M6 12h10',
  refresh: 'M20 11a8 8 0 0 0-14.9-3.5 M4 4v4h4 M4 13a8 8 0 0 0 14.9 3.5 M20 20v-4h-4',
}

export function Icon({ name, size = 20, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" style={{ flexShrink: 0 }} {...props}><path d={ICONS[name] || ICONS.grid} /></svg>
}

// Cropped from the approved brand boards; never the full boards with captions.
const BRAND = {
  horizontal: ['/assets/branding/sovereign-logo-horizontal.png', 508, 169],
  stacked: ['/assets/branding/sovereign-logo-stacked.png', 383, 299],
  mark: ['/assets/branding/sovereign-mark.png', 458, 458],
  primary: ['/assets/branding/sovereign-logo-primary.png', 768, 605],
}

export function Logo({ variant = 'horizontal', className = '', decorative = false, ...props }) {
  const [src, width, height] = BRAND[variant] || BRAND.horizontal
  return <img className={`brand-img ${className}`} src={src} width={width} height={height}
    alt={decorative ? '' : 'Sovereign AI Workbench'} decoding="async" {...props} />
}

export function AgentAvatar({ size = 40, className = '' }) {
  return <img className={`brand-img agent-avatar ${className}`} src="/assets/branding/agent-mark.png" width={size} height={size} alt="AI agent" decoding="async" />
}

export function PageHeader({ title, description, actions }) {
  return <header className="page-header">
    <div><h1 tabIndex={-1} data-page-title>{title}</h1>{description && <p className="page-description">{description}</p>}</div>
    {actions && <div className="page-actions">{actions}</div>}
  </header>
}

export function LoadingState({ label = 'Loading…' }) {
  return <div className="state state-loading" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" />{label}</div>
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }) {
  return <div className="state state-error" role="alert"><Icon name="alert" /><div><strong>{title}</strong>{message && <p>{message}</p>}
    {onRetry && <button type="button" onClick={() => onRetry()}>Try again</button>}</div></div>
}

export function EmptyState({ title, message, children }) {
  return <div className="state state-empty"><strong>{title}</strong>{message && <p>{message}</p>}{children}</div>
}

// Honest placeholder for capabilities whose UI or backend support has not landed yet. Never fake data.
export function PlannedCapability({ title, phase, available, planned, requires }) {
  return <section className="planned" aria-labelledby="planned-title">
    <span className="badge badge-planned">Not yet available · {phase}</span>
    <h2 id="planned-title">{title}</h2>
    {available && <p><strong>Available today:</strong> {available}</p>}
    {planned && <p><strong>Planned:</strong> {planned}</p>}
    {requires && <p className="muted"><strong>Requires:</strong> {requires}</p>}
    <p className="muted">No operational data is shown here until the backend provides it.</p>
  </section>
}

const useStatusTitle = text => useEffect(() => { document.title = `${text} · Sovereign AI Workbench` }, [text])

export function NotFound() {
  useStatusTitle('Page not found')
  return <div className="status-page"><h1 tabIndex={-1} data-page-title>Page not found</h1>
    <p>This address does not exist in the Sovereign AI Workbench (error 404).</p>
    <div className="toolbar"><Link className="button" to="/app/dashboard">Go to dashboard</Link><Link className="button ghost" to="/">Home</Link></div></div>
}

export function Forbidden() {
  useStatusTitle('Access restricted')
  return <div className="status-page"><h1 tabIndex={-1} data-page-title>Access restricted</h1>
    <p>Your server-assigned role does not permit this area (error 403). Roles are granted by an administrator, never by the browser.</p>
    <div className="toolbar"><Link className="button" to="/app/dashboard">Back to dashboard</Link></div></div>
}

export function RouteError() {
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) return <main id="main" className="standalone"><NotFound /></main>
  return <main id="main" className="standalone"><ErrorState title="This view failed to load"
    message="Reload the page. If the problem continues, check that the Workbench frontend and backend are running." onRetry={() => window.location.reload()} /></main>
}
