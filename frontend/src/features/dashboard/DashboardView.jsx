import { useMemo } from 'react'
import { Link } from 'react-router'
import { useResource } from '../../hooks/useApi.js'
import { BarList, ColumnChart } from '../../components/charts.jsx'
import { Icon } from '../../components/ui.jsx'
import { RequestState, SensorTrends, WorkOrderSummary } from '../maintenance/MaintenanceView.jsx'
import { GOVERNANCE_EVENTS, countBy, eventsPerDay, humanizeEvent } from '../insights/insightsModel.js'

const dayLabel = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
function ago(iso) {
  const minutes = Math.round((Date.parse(iso) - Date.now()) / 60000)
  if (Math.abs(minutes) < 60) return relative.format(minutes, 'minute')
  if (Math.abs(minutes) < 1440) return relative.format(Math.round(minutes / 60), 'hour')
  return relative.format(Math.round(minutes / 1440), 'day')
}

// Each signal reads as a sentence fragment with an honest state: checking, verified, attention, or unavailable.
function Signal({ state, label, value, to }) {
  const content = <><span className="signal-dot" data-state={state} aria-hidden="true" /><span className="signal-label">{label}</span><span className="signal-value">{value}</span></>
  return <li className="signal">{to ? <Link className="signal-inner" to={to}>{content}</Link> : <span className="signal-inner">{content}</span>}</li>
}

function SystemSignals({ health, reviewer }) {
  const ready = useResource('/ready')
  const models = useResource('/models/status')
  const proof = useResource('/sovereignty/proof')
  const verify = useResource(reviewer ? '/audit/verify' : null)
  const pending = r => !r.data && !r.error
  const readyChecks = ready.data?.checks ? Object.values(ready.data.checks) : []
  return <ul className="signals" aria-label="System status">
    <Signal state={health === 'Connected' ? 'ok' : health === 'Checking' ? 'pending' : 'bad'} label="Backend" value={health} />
    <Signal state={pending(ready) ? 'pending' : ready.data?.status === 'ready' ? 'ok' : 'warn'} label="Readiness"
      value={pending(ready) ? 'Checking…' : ready.data ? `${readyChecks.filter(Boolean).length}/${readyChecks.length} checks` : 'Unavailable'} />
    <Signal state={pending(models) ? 'pending' : models.data?.configured_model_present ? 'ok' : 'warn'} label="Local model"
      value={pending(models) ? 'Checking…' : models.data?.configured_model || 'Unavailable'} />
    <Signal state={pending(proof) ? 'pending' : proof.data?.external_ai_calls === 0 ? 'ok' : 'warn'} label="Hosted AI calls"
      value={pending(proof) ? 'Checking…' : proof.data?.external_ai_calls ?? 'Unavailable'} to="/app/sovereignty" />
    {reviewer && <Signal state={pending(verify) ? 'pending' : verify.data?.valid ? 'ok' : 'bad'} label="Audit chain"
      value={pending(verify) ? 'Verifying…' : verify.data ? (verify.data.valid ? `${verify.data.events_checked} events verified` : 'Verification failed') : 'Unavailable'} to="/app/audit" />}
  </ul>
}

function Card({ title, to, action, children, className = '' }) {
  return <section className={`dash-card ${className}`} aria-label={title}>
    <header><h2>{title}</h2>{to && <Link className="card-link" to={to}>{action}<Icon name="arrow" size={16} /></Link>}</header>
    {children}
  </section>
}

function ReviewQueue({ reviewer }) {
  const queue = useResource(reviewer ? '/approvals' : null)
  if (!reviewer) return <p className="muted">Your role submits questions; reviewers approve advisory drafts. Drafts you create appear in the reviewers' queue.</p>
  const items = queue.data || []
  return <RequestState request={queue} isEmpty={false}>
    <p className="queue-count"><b>{items.length}</b> {items.length === 1 ? 'draft awaits' : 'drafts await'} human review</p>
    {items.length ? <ul className="queue-list">{items.slice(0, 4).map(item => <li key={item.action_revision_id}>
      <span className="queue-route">{item.route}</span><span className="identifier muted small">{item.action_revision_id.slice(0, 8)}</span><span className="muted small">{ago(item.created_at)}</span>
    </li>)}</ul> : <p className="muted">The queue is clear.</p>}
  </RequestState>
}

export function GovernanceActivity() {
  const log = useResource('/audit/log?limit=500')
  const events = useMemo(() => log.data || [], [log.data])
  const perDay = useMemo(() => eventsPerDay(events), [events])
  const governance = useMemo(() => countBy(events.filter(e => GOVERNANCE_EVENTS.test(e.event_type)), e => humanizeEvent(e.event_type)), [events])
  return <RequestState request={log} isEmpty={!events.length} empty="No audit events recorded yet.">
    <ColumnChart data={perDay} height={140} label="Audit events per day" format={t => dayLabel.format(t)} unitLabel="events" />
    <h3 className="dash-subhead">Governance events</h3>
    <BarList data={governance} label="Governance events by type" limit={6} />
  </RequestState>
}

function AgentRoutes() {
  const agents = useResource('/agents/status')
  const routes = agents.data?.routes || []
  return <RequestState request={agents} isEmpty={!routes.length} empty="No agent routes reported.">
    <p className="route-summary"><span><b>{routes.filter(r => r.status === 'implemented').length}</b> specialist routes</span>
      <span><b>{routes.filter(r => r.status === 'guardrail').length}</b> guardrails that stop unsafe or incomplete requests</span></p>
  </RequestState>
}

export function DashboardView({ user, health }) {
  const reviewer = ['reviewer', 'admin'].includes(user?.role)
  return <div className="dash">
    <SystemSignals health={health} reviewer={reviewer} />
    <div className="dash-grid">
      <Card title="Vibration trend" to="/app/maintenance" action="Maintenance & Sensors" className="span-2"><SensorTrends compact /></Card>
      <div className="dash-stack">
        <Card title="Review queue" to={reviewer ? '/app/approvals' : '/app/workspace'} action={reviewer ? 'Open desk' : 'Ask a question'}><ReviewQueue reviewer={reviewer} /></Card>
        <Card title="Agent routes" to="/app/agents" action="Agents"><AgentRoutes /></Card>
      </div>
      <Card title="Work orders" to="/app/maintenance" action="Open board"><WorkOrderSummary /></Card>
      {reviewer && <Card title="Governance activity" to="/app/audit" action="Audit log" className="span-2"><GovernanceActivity /></Card>}
    </div>
  </div>
}
