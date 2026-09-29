// Single source of truth for workbench navigation and role-restricted routes.
// Hiding a link is a convenience only: the backend authorizes every request.
export const REVIEWERS = ['reviewer', 'admin']
export const ADMINS = ['admin']

export const APP_SECTIONS = [
  { group: 'Operate', items: [
    { path: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { path: 'workspace', label: 'AI Workspace', icon: 'terminal' },
    { path: 'workspace/voice', label: 'Voice query', icon: 'mic' },
    { path: 'agents', label: 'Agents', icon: 'agent' },
  ] },
  { group: 'Evidence', items: [
    { path: 'pid', label: 'P&ID Intelligence', icon: 'drawing' },
    { path: 'maintenance', label: 'Maintenance & Sensors', icon: 'pulse' },
    { path: 'operations', label: 'Operations', icon: 'tool' },
  ] },
  { group: 'Knowledge', items: [
    { path: 'knowledge', label: 'Knowledge', icon: 'book' },
    { path: 'gaps', label: 'Knowledge Gaps', icon: 'gap' },
  ] },
  { group: 'Govern', items: [
    { path: 'approvals', label: 'Approvals', icon: 'check' },
    { path: 'executions', label: 'Executions', icon: 'timeline' },
    { path: 'audit', label: 'Audit', icon: 'list', roles: REVIEWERS },
  ] },
  { group: 'Trust', items: [
    { path: 'sovereignty', label: 'Sovereignty', icon: 'shield' },
    { path: 'resources', label: 'Government Resources', icon: 'globe' },
  ] },
  { group: 'Admin', items: [
    { path: 'admin', label: 'Administration', icon: 'users', roles: ADMINS },
  ] },
]

export const canAccess = (roles, role) => !roles?.length || roles.includes(role)

export function navigationFor(role) {
  return APP_SECTIONS
    .map(section => ({ ...section, items: section.items.filter(item => canAccess(item.roles, role)) }))
    .filter(section => section.items.length)
}

export function guardDecision(session, roles) {
  if (!session || session.status === 'loading') return 'loading'
  if (session.status === 'unavailable') return 'unavailable'
  if (session.status !== 'authenticated' || !session.user) return 'login'
  return canAccess(roles, session.user.role) ? 'allow' : 'forbidden'
}

// Post-login redirect: only same-app paths, never protocol-relative or external URLs.
export function safeNext(next) {
  if (typeof next !== 'string' || !/^\/app(?:\/|\?|#|$)/.test(next) || next.includes('\\')) return '/app/dashboard'
  const url = new URL(next, 'http://workbench.local')
  return url.pathname === '/app' || url.pathname.startsWith('/app/') ? url.pathname + url.search + url.hash : '/app/dashboard'
}

export function sessionFromError(error) {
  return error?.status === 401 ? { status: 'anonymous', user: null, error: null } : { status: 'unavailable', user: null, error }
}

// Command palette ranking: prefix match first, then substring, then initials ("kg" → Knowledge Gaps).
export function matchCommands(commands, query) {
  const q = query.trim().toLowerCase()
  if (!q) return commands
  return commands
    .map(command => {
      const text = `${command.label} ${command.group} ${command.keywords || ''}`.toLowerCase()
      const at = text.indexOf(q)
      const initials = command.label.toLowerCase().split(/\s+/).map(w => w[0]).join('')
      return { command, score: at === 0 ? 0 : at > 0 ? 1 + at / 100 : initials.startsWith(q) ? 2 : -1 }
    })
    .filter(entry => entry.score >= 0)
    .sort((a, b) => a.score - b.score)
    .map(entry => entry.command)
}
