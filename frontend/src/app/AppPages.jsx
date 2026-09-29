import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useSession } from './session.jsx'
import { REVIEWERS } from './navigation.js'
import { AgentAvatar, EmptyState, NotFound, PageHeader, PlannedCapability } from '../components/ui.jsx'
import { ApiState, Audit, DataView, Knowledge, QueryConsole, Sovereignty } from '../WorkspacePages.jsx'
import { OperationalWorkspace } from '../OperationalPages.jsx'
import { AutomationStatus, BIReport, LanguageSelector } from '../ProductPages.jsx'
import { useRequest, useResource } from '../hooks/useApi.js'
import { useBackendHealth } from '../hooks/useBackendHealth.js'
import { DashboardView, GovernanceActivity } from '../features/dashboard/DashboardView.jsx'
import { SensorTrends, WorkOrderBoard } from '../features/maintenance/MaintenanceView.jsx'
import { ReviewDesk } from '../features/approvals/ReviewDesk.jsx'
import { AgentsView } from '../features/agents/AgentsView.jsx'

// Pages wrap existing, backend-connected components. Unfinished areas say so plainly; nothing is fabricated.
export function DashboardPage() {
  const { user } = useSession()
  const { status } = useBackendHealth()
  const reviewer = REVIEWERS.includes(user?.role)
  const bi = useResource(reviewer ? '/bi/operational' : null)
  const today = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())
  return <>
    <PageHeader title="Dashboard" description={`${today} · live from this Workbench. Every figure below is read from the local backend.`} />
    <DashboardView user={user} health={status} />
    {reviewer && <details className="panel disclosure"><summary><h2>Stored operational BI</h2><span className="muted small">Sampled run metadata, advisory only</span></summary><ApiState request={bi} /><BIReport data={bi.data} /></details>}
  </>
}

export function WorkspacePage() {
  const { user } = useSession()
  return <><PageHeader title="AI Workspace" description="Ask a governed question. Answers cite their evidence and anything operational is held for human review." />
    <QueryConsole user={user} /></>
}

export function VoiceWorkspacePage() {
  const { user } = useSession()
  return <><PageHeader title="Voice query" description="Local speech-to-text only. Every transcript is reviewed by you before it can be submitted." />
    <QueryConsole user={user} voiceFocus /></>
}

export function AgentsPage() {
  return <><PageHeader title="Agents" description="Configured specialist routes and read-only tools reported by the backend." actions={<AgentAvatar size={56} />} />
    <AgentsView /></>
}

export function PidPage() {
  return <><PageHeader title="P&ID Intelligence" />
    <PlannedCapability title="Interactive P&ID evidence viewer" phase="Phase F6"
      available={<>P&ID regions appear as cited, as-drawn evidence in <Link to="/app/workspace">AI Workspace</Link> results.</>}
      planned="Drawing viewer with OCR regions, visual candidates, registry matches, conflicts and review indicators."
      requires="Read-only drawing and region endpoints in the backend." /></>
}

export function MaintenancePage() {
  return <><PageHeader title="Maintenance & Sensors" description="Sensor readings and work orders from the local system of record, each traceable to its source row." />
    <section className="panel"><div className="section-heading"><h2>Sensor trends</h2><span className="muted small">Hover or use the arrow keys to read exact values</span></div><SensorTrends /></section>
    <section className="panel"><div className="section-heading"><h2>Work orders</h2></div><WorkOrderBoard /></section></>
}

const OPERATION_VIEWS = { handover: 'Shift Handover', compliance: 'Environmental Compliance', notes: 'Operator Notes' }
export function OperationsPage() {
  const { user } = useSession()
  const { view } = useParams()
  const navigate = useNavigate()
  if (!OPERATION_VIEWS[view]) return <NotFound />
  const change = label => {
    if (label === 'Knowledge Gaps') return navigate('/app/gaps')
    navigate(`/app/operations/${Object.keys(OPERATION_VIEWS).find(key => OPERATION_VIEWS[key] === label)}`)
  }
  return <><PageHeader title="Operations" description="Shift handover, environmental compliance and operator notes. Advisory only." />
    <OperationalWorkspace user={user} view={OPERATION_VIEWS[view]} onViewChange={change} /></>
}

export function KnowledgePage() {
  return <><PageHeader title="Knowledge" description="Retrieve cited evidence from locally indexed documents." />
    <Knowledge />
    <p className="muted">The Verified Knowledge registry lifecycle view (candidate, verified, stale, revoked) arrives in Phase F5.</p></>
}

export function GapsPage() {
  const gaps = useResource('/knowledge-gaps')
  return <><PageHeader title="Knowledge Gaps" description="Evidence gaps recorded by governed runs. Resolving a gap requires verified knowledge or an authoritative source." actions={<button type="button" onClick={gaps.refresh}>Refresh</button>} />
    <section className="panel"><ApiState request={gaps} empty="No knowledge gaps recorded." />{gaps.data?.length ? <DataView value={gaps.data} /> : null}
      <p className="muted">The lifecycle board with review actions arrives in Phase F5.</p></section></>
}

export function ApprovalsPage() {
  const { user } = useSession()
  return <><PageHeader title="Approvals" description="Human approval releases advisory output only. No plant or equipment action is ever executed." />
    <ReviewDesk user={user} /></>
}

export function ExecutionsPage() {
  const lookup = useRequest()
  const [id, setId] = useState('')
  return <><PageHeader title="Durable executions" description="Checkpointed graph runs you own. No reasoning traces are stored or shown." />
    <section className="panel">
      <form className="toolbar" onSubmit={event => { event.preventDefault(); lookup.run(`/executions/${encodeURIComponent(id.trim())}`) }}>
        <label>Execution ID<input value={id} onChange={event => setId(event.target.value)} required pattern="[0-9a-fA-F-]{36}" /></label>
        <button disabled={lookup.loading || !id.trim()}>Look up execution</button>
      </form>
      <ApiState request={lookup} />{lookup.data && <DataView value={lookup.data} />}
      <p className="muted">A list of executions and the timeline view arrive with the execution list endpoint (Phase F5).</p>
    </section></>
}

export function AuditPage() {
  return <><PageHeader title="Audit" description="Tamper-evident, not tamper-proof: modification of the recorded chain is detectable." />
    <section className="panel"><div className="section-heading"><h2>Activity</h2></div><GovernanceActivity /></section><Audit /></>
}

export function SovereigntyPage() {
  const proof = useResource('/sovereignty/proof')
  return <><PageHeader title="Sovereignty" description="Offline-capable, not automatically air-gapped: network isolation is enforced by site controls." /><Sovereignty proof={proof} /></>
}

const POLICY = [
  ['AIKosh', 'Resource registry', 'Downloaded resources need provenance, licence, a named approver and a pinned SHA-256 before local approval.'],
  ['BHASHINI', 'Public data only · disabled for confidential data', 'Off by default. No BHASHINI client ships in this build.'],
  ['data.gov.in', 'Optional public connector', 'Requires public deployment mode, the feature flag and an explicitly public request. Never receives plant data.'],
  ['API Setu', 'Interface-ready', 'No live integration is claimed.'],
  ['DigiLocker', 'Evaluated · future', 'Not part of confidential inference.'],
]
export function ResourcesPage() {
  const status = useResource('/product/status')
  const resources = status.data?.language_resources || []
  return <><PageHeader title="Government Resources" description="Classification is enforced by the server. Confidential data may only use LOCAL_APPROVED resources." />
    <section className="panel"><h2>Policy</h2><ul className="policy-list">{POLICY.map(([name, state, note]) => <li key={name}><strong>{name}</strong><span className="badge">{state}</span><p>{note}</p></li>)}</ul></section>
    <section className="panel"><h2>Language resources reported by this Workbench</h2><ApiState request={status} />
      {resources.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Language resources"><table><thead><tr><th>Resource</th><th>Provider</th><th>Classification</th><th>Confidential data</th></tr></thead>
        <tbody>{resources.map(r => <tr key={r.name}><td>{r.name}</td><td>{r.provider}</td><td><code>{r.classification}</code></td><td>{r.confidential_eligible ? 'Allowed' : 'Never'}</td></tr>)}</tbody></table></div>
        : status.data && <EmptyState title="No resources reported" />}
      {status.data && <AutomationStatus data={status.data} />}</section></>
}

export function AdminPage() {
  return <><PageHeader title="Administration" />
    <PlannedCapability title="User and account administration" phase="Phase F7"
      planned="Create and deactivate users, change roles, approve sign-ups, issue recovery codes and revoke sessions."
      requires="Account migration 0017 and the audited admin API." /></>
}

export function ProfilePage() {
  const { user, signOut } = useSession()
  const navigate = useNavigate()
  return <><PageHeader title="Profile" />
    <section className="panel"><DataView value={{ username: user?.username, server_role: user?.role }} />
      <p className="muted">Roles are assigned by an administrator on the server. Password change and linked accounts arrive with the account migration.</p>
      <div className="toolbar"><LanguageSelector /><button type="button" onClick={async () => { await signOut(); navigate('/login', { replace: true }) }}>Sign out</button></div>
    </section></>
}
