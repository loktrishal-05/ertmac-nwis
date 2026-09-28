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
  if (typeof next !== 'string' || !next.startsWith('/app') || next.startsWith('//') || next.includes('\\')) return '/app/dashboard'
  return next
}

export function sessionFromError(error) {
  return error?.status === 401 ? { status: 'anonymous', user: null, error: null } : { status: 'unavailable', user: null, error }
}
