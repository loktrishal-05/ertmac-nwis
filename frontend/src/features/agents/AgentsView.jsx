import { useResource } from '../../hooks/useApi.js'
import { Icon } from '../../components/ui.jsx'
import { RequestState } from '../maintenance/MaintenanceView.jsx'

// Configured capability, not live activity: routes grouped by what they do, with the real local runtime.
const ROUTE_ICON = { knowledge: 'book', maintenance: 'tool', safety: 'shield', process_optimization: 'pulse', combined_safety_maintenance: 'shield',
  shift_handover: 'timeline', environmental_compliance: 'globe', guardrail_refusal: 'lock', clarification: 'alert' }
const label = route => route.replaceAll('_', ' ').replace(/^\w/, c => c.toUpperCase())

function RouteCard({ route }) {
  return <li className="route-card" data-status={route.status}>
    <span className="route-icon" aria-hidden="true"><Icon name={ROUTE_ICON[route.route] || 'agent'} size={18} /></span>
    <div><h3>{label(route.route)}</h3><p>{route.description}</p></div>
  </li>
}

export function AgentsView() {
  const request = useResource('/agents/status')
  const routes = request.data?.routes || []
  const specialists = routes.filter(r => r.status === 'implemented')
  const guardrails = routes.filter(r => r.status === 'guardrail')
  const other = routes.filter(r => r.status !== 'implemented' && r.status !== 'guardrail')
  const gateway = request.data?.gateway
  const tools = request.data?.tools || []
  return <RequestState request={request} isEmpty={!routes.length} empty="No agent routes reported.">
    {gateway && <ul className="runtime-strip" aria-label="Local model runtime">
      <li><span className="signal-dot" data-state={gateway.reachable ? 'ok' : 'bad'} aria-hidden="true" /><b>{gateway.runtime}</b> {gateway.runtime_version} · {gateway.reachable ? 'reachable' : 'unreachable'}</li>
      <li>Configured <code className="identifier">{gateway.configured_model}</code>{gateway.configured_model_present ? '' : ' (not installed)'}</li>
      <li>Available {(gateway.available_models || []).map(m => <code key={m} className="identifier">{m}</code>)}</li>
    </ul>}
    <section className="route-group" aria-labelledby="specialists"><header><h2 id="specialists">Specialist routes</h2><span className="count">{specialists.length}</span><p className="muted small">A question is routed to one specialist; its output is advisory and cites evidence.</p></header>
      <ul className="route-grid">{specialists.map(route => <RouteCard key={route.route} route={route} />)}</ul></section>
    {!!guardrails.length && <section className="route-group" aria-labelledby="guardrails"><header><h2 id="guardrails">Guardrails</h2><span className="count">{guardrails.length}</span><p className="muted small">Requests that are unsafe, out of scope or missing essentials stop here instead of reaching a model.</p></header>
      <ul className="route-grid">{guardrails.map(route => <RouteCard key={route.route} route={route} />)}</ul></section>}
    {!!other.length && <section className="route-group"><header><h2>Other routes</h2></header><ul className="route-grid">{other.map(route => <RouteCard key={route.route} route={route} />)}</ul></section>}
    {!!tools.length && <details className="panel disclosure tools-disclosure"><summary><h2>Read-only tools</h2><span className="muted small">{tools.length} deterministic tools; none can change plant state</span></summary>
      <ul className="tool-list">{tools.map(tool => <li key={tool.name}><code className="identifier">{tool.name}</code><p>{tool.description}</p></li>)}</ul></details>}
  </RequestState>
}
