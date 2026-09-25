import { useState } from 'react'
import { useLanguage } from './language.js'
import { VoiceControls } from './ProductPages.jsx'
import { useRequest, useResource } from './hooks/useApi.js'

export function ApiState({ request, empty = 'No records returned.' }) {
  if (request.loading) return <p role="status">Loading…</p>
  if (request.error) return <p className="api-error" role="alert">{request.error.status === 401 ? 'Sign in to access this data.' : request.error.status === 403 ? `Access denied: ${request.error.message}` : request.error.message}</p>
  if (request.data && typeof request.data === 'object' && !Object.keys(request.data).length) return <p>{empty}</p>
  return null
}

export function DataView({ value }) {
  if (value == null) return <span className="muted">Unavailable</span>
  if (Array.isArray(value)) return value.length ? <ul className="data-list">{value.map((item, index) => <li key={index}><DataView value={item} /></li>)}</ul> : <span className="muted">None returned</span>
  if (typeof value === 'object') return <dl className="data-fields">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><DataView value={item} /></dd></div>)}</dl>
  return <span>{typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}</span>
}

function Evidence({ items = [] }) {
  return <section><h3>Citations / source evidence</h3>{!items.length && <p>No source evidence returned.</p>}{items.map((item, index) => <details key={item.evidence_id || index}><summary>{item.source_filename || item.evidence_id || `Source ${index + 1}`} — {item.locator || 'Locator in details'}</summary><DataView value={item} /></details>)}</section>
}

export function ExecutionPanel({ execution }) {
  if (!execution) return null
  const paths = { VERIFIED_FAST_PATH: 'Verified', CAG_PATH: 'CAG', HYBRID_RAG_PATH: 'Hybrid RAG', MGS_PATH: 'MGS', EXISTING_AGENTIC_PATH: 'Agentic' }
  const coverage = execution.evidence_sufficiency || {}
  return <aside className="review-notice" aria-label="Execution and evidence">
    <strong>Execution: {paths[execution.execution_path] || 'Unavailable'}</strong>
    <p>Evidence: {coverage.state || 'Unavailable'} ? Sources: {execution.retrieved_sources ?? 'Unavailable'} ? Model: {execution.model_used?.join(', ') || 'No inference recorded'} ? Latency: {Number.isFinite(execution.total_latency_ms) ? `${(execution.total_latency_ms / 1000).toFixed(2)} s` : 'Unavailable'}</p>
    {!!coverage.missing_categories?.length && <p>Missing evidence: {coverage.missing_categories.join(', ')}</p>}
    {!!coverage.issues?.length && <p>Coverage limits: {coverage.issues.join(', ')}</p>}
    {execution.fallback_used && <p>Safe fallback used.</p>}
    <p>Evidence coverage is not permission to operate equipment.</p>
  </aside>
}

export function Result({ data }) {
  if (!data) return null
  const review = data.human_approval_required || data.human_review_required || data.presentation === 'DRAFT' || data.governance_status === 'PENDING_REVIEW'
  const refusal = data.agent_result?.schema === 'S5' ? data.agent_result.output?.status : null
  return <div className="result" aria-live="polite">
    {refusal && <p className="review-notice">{refusal.replaceAll('_', ' ')}</p>}
    <p className={review ? 'review-notice' : 'result-status'}>{review ? 'DRAFT — Human approval required. Advisory recommendation only.' : (data.governance_status || 'Backend response')}</p>
    <DataView value={{ route: data.route, revision: data.action_revision_id, evidence_status: data.evidence_binding_status }} />
    <h3>Agent result</h3><DataView value={data.agent_result} />
    {!!data.warnings?.length && <><h3>Warnings</h3><DataView value={data.warnings} /></>}
    <ExecutionPanel execution={data.execution} />
    <Evidence items={data.evidence} />
    <details><summary>Complete response / revision hashes</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
  </div>
}

export function Auth({ auth }) {
  const action = useRequest()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  async function login(event) {
    event.preventDefault()
    const result = await action.run('/auth/login', { method: 'POST', body: { username, password } })
    setPassword('')
    if (result) auth.refresh()
  }
  async function logout() {
    if (await action.run('/auth/logout', { method: 'POST' })) auth.refresh()
  }
  return <section className="panel auth-panel" aria-label="Account">
    {auth.data ? <div className="toolbar"><span>Signed in: <strong>{auth.data.username}</strong> · {auth.data.role} (server role)</span><button onClick={logout} disabled={action.loading}>Sign out</button></div> : <form className="toolbar" onSubmit={login}><label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required maxLength={100} /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={255} /></label><button disabled={action.loading || auth.loading}>Sign in</button><span>Sign in before requesting a governed recommendation.</span></form>}
    {auth.error?.status !== 401 && <ApiState request={auth} />}<ApiState request={action} />
  </section>
}

export function Dashboard({ proof, health, user }) {
  const ready = useResource('/ready')
  const agents = useResource('/agents/status')
  const reviewer = ['reviewer', 'admin'].includes(user?.role)
  const approvals = useResource(reviewer ? '/approvals' : null)
  const metrics = [
    ['Backend', health, 'Process liveness'], ['Readiness', ready.data?.status || ready.error?.data?.status, 'Dependencies checked without inference'],
    ['Implemented routes', agents.data?.routes?.filter(r => r.status === 'implemented').length, 'Running-agent count unavailable'],
    ['Pending approvals', approvals.data?.length, reviewer ? 'Current review queue' : 'Reviewer sign-in required'],
    ['Indexed documents', null, 'No inventory-count API available'], ['External AI calls', proof.data?.external_ai_calls, 'Current backend process only'],
  ]
  return <><section className="metrics">{metrics.map(([label, value, caption]) => <article className="metric" key={label}><div className="metric-label">{label}</div><div className="metric-value">{value ?? 'Unavailable'}</div><p>{caption}</p></article>)}</section>
    <section className="panel"><div className="section-heading"><h2>Runtime overview</h2><button onClick={() => { ready.refresh(); agents.refresh(); approvals.refresh(); proof.refresh() }}>Refresh overview</button></div>
      <ApiState request={ready} />{ready.error?.data && <DataView value={ready.error.data} />}<ApiState request={agents} />{reviewer && <ApiState request={approvals} />}<ApiState request={proof} />
      <DataView value={{ sovereignty: proof.data?.status, model: proof.data?.local_model, ready: ready.data?.checks }} />
      <p>Agent execution activity is not reported by the status API. This view shows configured capabilities.</p></section></>
}

export function QueryConsole({ user }) {
  const { language, t } = useLanguage()
  const [channel, setChannel] = useState('text')
  const [query, setQuery] = useState('')
  const request = useRequest()
  async function submit(event) {
    event.preventDefault()
    await request.run('/query', { method: 'POST', body: { query, request_id: crypto.randomUUID(), input_language: language, input_channel: channel }, timeout: 660000 })
  }
  return <section className="panel"><h2>{t('Ask the workbench')}</h2><p>Answers are advisory. Refusals and clarification requests are shown as returned.</p>{!user && <p className="review-notice">Anonymous queries cannot produce reviewable approvals. Sign in first for governed recommendations.</p>}
    <VoiceControls key={request.data?.run_id || 'input'} user={user} onTranscript={text => { setQuery(text); setChannel('voice') }} result={request.data} />
    <form onSubmit={submit}><label>{t('Question')}<textarea value={query} onChange={e => setQuery(e.target.value)} required maxLength={10000} rows={4} /></label><button disabled={request.loading || !query.trim()}>{t('Submit query')}</button></form>
    {request.loading && <p>Local inference may take several minutes. Keep this page open.</p>}<ApiState request={request} /><Result data={request.data} />
  </section>
}

export function Agents() {
  const request = useResource('/agents/status')
  return <section className="panel"><div className="section-heading"><h2>Agent capabilities</h2><button disabled={request.loading} onClick={request.refresh}>Refresh agents</button></div><ApiState request={request} />
    {request.data && <><p>Configured routes, not a live activity feed.</p>{!request.data.routes?.length && <p>No agent routes returned.</p>}<div className="agent-grid">{request.data.routes?.map(route => <article className="agent-card" key={route.route}><h3>{route.route.replaceAll('_', ' ')}</h3><p>{route.description}</p><div className="agent-footer">{route.status}</div></article>)}</div><details><summary>Read-only tools and model runtime</summary><DataView value={{ tools: request.data.tools, gateway: request.data.gateway }} /></details></>}
  </section>
}

export function Approvals({ user }) {
  const queue = useResource('/approvals')
  const detail = useRequest()
  const action = useRequest()
  const [revision, setRevision] = useState('')
  const [comment, setComment] = useState('')
  const reviewer = ['reviewer', 'admin'].includes(user?.role)
  const current = detail.data
  const busy = detail.loading || action.loading
  async function open(id) { action.reset(); setComment(''); setRevision(id); await detail.run(`/approvals/${encodeURIComponent(id)}`) }
  async function decide(decision) {
    const id = current.action_revision_id
    const result = await action.run(`/approvals/${id}/decision`, { method: 'POST', body: { decision, expected_revision_id: id, reviewer_comment: comment || null } })
    if (result) { await detail.run(`/approvals/${id}`); queue.refresh() }
  }
  return <section className="panel"><div className="section-heading"><h2>Advisory review queue</h2><button onClick={queue.refresh} disabled={queue.loading}>Refresh queue</button></div><p>Human approval releases only an advisory recommendation. No equipment-control action exists here.</p><ApiState request={queue} empty="No pending revisions returned." />
    <ul className="data-list">{queue.data?.map(row => <li key={row.action_revision_id}><button disabled={busy} onClick={() => open(row.action_revision_id)}>Review {row.action_revision_id}</button><span> {row.route} · {new Date(row.created_at).toLocaleString()}</span></li>)}</ul>
    <form className="toolbar" onSubmit={e => { e.preventDefault(); open(revision) }}><label>Revision ID (including previously decided revisions)<input required value={revision} onChange={e => setRevision(e.target.value)} /></label><button disabled={busy || !revision.trim()}>Load revision</button></form>
    <ApiState request={detail} />
    {current && <><h3>Exact revision</h3><DataView value={{ revision: current.action_revision_id, status: current.governance_status, requester: current.requester_user_id, request_hash: current.canonical_request_hash, proposal_hash: current.canonical_proposal_hash, evidence_status: current.evidence_binding_status, manifest_hash: current.evidence_manifest_hash }} /><Result data={current} />
      <DataView value={{ decisions: current.decisions }} /><label>Reviewer comment<textarea maxLength={2000} value={comment} onChange={e => setComment(e.target.value)} /></label>
      <div className="toolbar">{reviewer && current.governance_status === 'PENDING_REVIEW' && <><button disabled={busy || current.requester_user_id === user.id} onClick={() => decide('approve')}>Approve advisory</button><button disabled={busy || current.requester_user_id === user.id} onClick={() => decide('reject')}>Reject advisory</button></>}
        {reviewer && current.governance_status === 'APPROVED' && <button disabled={busy} onClick={() => decide('revoke')}>Revoke approval</button>}
        {user && current.governance_status === 'APPROVED' && <button disabled={busy} onClick={() => action.run(`/approvals/${current.action_revision_id}/release`)}>View approved advisory</button>}</div>
      {current.requester_user_id === user?.id && <p>Self-approval is prohibited by the backend.</p>}</>}
    <ApiState request={action} />{action.data && <details open><summary>Latest server action result — {action.data.action_revision_id}</summary><DataView value={action.data} /></details>}
  </section>
}

export function Knowledge() {
  const search = useRequest()
  const ingest = useRequest()
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [title, setTitle] = useState('')
  return <section className="panel"><h2>Local knowledge and documents</h2><form onSubmit={e => { e.preventDefault(); search.run('/knowledge/retrieve', { method: 'POST', body: { query }, timeout: 180000 }) }}><label>Search source evidence<input value={query} onChange={e => setQuery(e.target.value)} required maxLength={2000} /></label><button disabled={search.loading}>Retrieve evidence</button></form><ApiState request={search} />
    {search.data && <><p>{search.data.results?.length ?? 0} matching chunks returned.</p><DataView value={search.data} /></>}
    <details><summary>Ingest an existing local PDF</summary><p>Path relative to the backend's data/raw directory. No browser or cloud upload. The server validates the path.</p><form onSubmit={e => { e.preventDefault(); ingest.run('/documents/ingest', { method: 'POST', body: { source_path: source, title, document_type: 'other' }, timeout: 660000 }) }}><label>Local PDF path<input value={source} onChange={e => setSource(e.target.value)} required maxLength={500} /></label><label>Document title<input value={title} onChange={e => setTitle(e.target.value)} required maxLength={200} /></label><button disabled={ingest.loading}>Ingest local PDF</button></form><ApiState request={ingest} />{ingest.data && <DataView value={ingest.data} />}</details>
  </section>
}

export function Audit() {
  const log = useResource('/audit/log?limit=100')
  const verify = useResource('/audit/verify')
  return <section className="panel"><div className="section-heading"><h2>Tamper-Evident Audit</h2><button disabled={log.loading || verify.loading} onClick={() => { log.refresh(); verify.refresh() }}>Refresh audit</button></div><p>Latest 100 events. Verification is a snapshot and may precede newly appended events.</p><ApiState request={verify} />{verify.data && <><p className={verify.data.valid ? 'result-status' : 'api-error'}>Chain verification: {verify.data.valid ? 'VALID' : 'FAILED'}</p><DataView value={verify.data} /></>}<ApiState request={log} />
    {log.data?.map(event => <details key={event.id}><summary>#{event.sequence_number} · {event.event_type} · {new Date(event.occurred_at).toLocaleString()} · {event.actor_id || event.actor_kind}</summary><DataView value={event} /></details>)}
  </section>
}

export function Sovereignty({ proof }) {
  const ready = useResource('/ready')
  const health = useResource('/health')
  return <section className="panel"><div className="section-heading"><h2>Application-level sovereignty</h2><button onClick={() => { proof.refresh(); ready.refresh(); health.refresh() }}>Refresh proof</button></div><p>No OS/firewall isolation is claimed. External hosted-AI dispatch counts cover the stated backend process observation window.</p><ApiState request={proof} />{proof.data && <DataView value={proof.data} />}<h3>Readiness</h3><ApiState request={ready} />{(ready.data || ready.error?.data) && <DataView value={ready.data || ready.error.data} />}<h3>Backend health</h3><ApiState request={health} />{health.data && <DataView value={health.data} />}</section>
}
