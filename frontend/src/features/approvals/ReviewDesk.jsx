import { useEffect, useState } from 'react'
import { useRequest, useResource } from '../../hooks/useApi.js'
import { EmptyState, ErrorState, Icon, LoadingState } from '../../components/ui.jsx'
import { DataView } from '../../WorkspacePages.jsx'

// The reviewer's desk: the queue on the left, one exact revision on the right, and a decision bar that is
// always in reach. Approval releases advisory output only; the backend enforces every rule shown here.

const STATUS = {
  PENDING_REVIEW: ['Awaiting review', 'warn'], APPROVED: ['Approved', 'ok'], REJECTED: ['Rejected', 'bad'],
  REVOKED: ['Revoked', 'muted'], RELEASED: ['Released', 'ok'],
}
const BINDING = { VERIFIED: ['Evidence integrity-bound', 'ok'], BOUND: ['Evidence integrity-bound', 'ok'], LEGACY_UNVERIFIED: ['Evidence not integrity-bound', 'warn'] }
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
function ago(iso) {
  if (!iso) return ''
  const minutes = Math.round((Date.parse(iso) - Date.now()) / 60000)
  if (Math.abs(minutes) < 60) return relative.format(minutes, 'minute')
  if (Math.abs(minutes) < 1440) return relative.format(Math.round(minutes / 60), 'hour')
  return relative.format(Math.round(minutes / 1440), 'day')
}
const title = route => `${(route || 'Advisory').replaceAll('_', ' ').replace(/^\w/, c => c.toUpperCase())} advisory`

function Chip({ tone, children }) { return <span className="chip-status" data-tone={tone}>{children}</span> }

function Advisory({ revision }) {
  const output = revision.agent_result?.output
  if (!output || typeof output !== 'object') return <DataView value={revision.agent_result} />
  const confidence = typeof output.overall_confidence === 'number' ? Math.round(output.overall_confidence * 100) : null
  const lists = [['Observations', output.observations, 'recorded, cited below'], ['Hypotheses', output.hypotheses, 'tentative; correlation is not causation'], ['Recommended checks', output.recommended_checks, 'verification a person performs']]
  return <div className="advisory">
    {confidence != null && <div className="confidence"><span>Model-reported confidence</span><span className="confidence-track" aria-hidden="true"><span style={{ width: `${confidence}%` }} /></span><b>{confidence}%</b></div>}
    {lists.map(([name, items, hint]) => <section key={name} className="advisory-block">
      <h4>{name} <small>{hint}</small></h4>
      {Array.isArray(items) && items.length ? <ul>{items.map((item, i) => <li key={i}>{typeof item === 'string' ? item : item?.text || JSON.stringify(item)}</li>)}</ul> : <p className="muted small">None returned.</p>}
    </section>)}
    {output.status && <p className="review-notice">{String(output.status).replaceAll('_', ' ')}{output.reason ? `: ${output.reason}` : ''}</p>}
  </div>
}

function EvidenceCards({ items = [] }) {
  if (!items.length) return <p className="muted">No source evidence returned.</p>
  const drawn = items.some(item => item.ocr_derived || item.kind === 'pid_region')
  return <>
    {drawn && <p className="review-notice">P&amp;ID / OCR evidence is as drawn only. It does not prove field topology, connectivity, isolation, valve state, permits, or readiness.</p>}
    <ol className="evidence-grid">{items.map((item, index) => <li key={item.evidence_id || index} className="evidence-card">
      <header><span className="evidence-index">{index + 1}</span><span className="evidence-file">{item.source_filename || item.evidence_id}</span>
        <span className="muted small">{item.locator || (item.page_start ? `page ${item.page_start}` : '')}</span></header>
      {item.section_path?.length ? <p className="evidence-path">{item.section_path.join(' › ')}</p> : null}
      {item.quote && <blockquote>{item.quote.length > 280 ? `${item.quote.slice(0, 280)}…` : item.quote}</blockquote>}
      <footer>{item.ocr_derived && <Chip tone="warn">OCR-derived{item.ocr_confidence != null ? ` · ${Math.round(item.ocr_confidence * 100)}%` : ''}</Chip>}
        {item.kind && <span className="muted small">{item.kind.replaceAll('_', ' ')}</span>}
        {item.source_sha256 && <code className="muted small" title={item.source_sha256}>sha256 {item.source_sha256.slice(0, 10)}…</code>}</footer>
    </li>)}</ol>
  </>
}

function ReviewPane({ revision, user, onDecided }) {
  const action = useRequest()
  const [comment, setComment] = useState('')
  const [ack, setAck] = useState(false)
  const reviewer = ['reviewer', 'admin'].includes(user?.role)
  const own = !!revision.requester_user_id && revision.requester_user_id === user?.id
  const [statusLabel, statusTone] = STATUS[revision.governance_status] || [String(revision.governance_status), 'muted']
  const [bindingLabel, bindingTone] = BINDING[revision.evidence_binding_status] || [String(revision.evidence_binding_status || 'Evidence binding unknown').replaceAll('_', ' '), 'muted']
  const unbound = bindingTone !== 'ok'
  const pending = revision.governance_status === 'PENDING_REVIEW'
  async function decide(decision) {
    const id = revision.action_revision_id
    const result = await action.run(`/approvals/${id}/decision`, { method: 'POST', body: { decision, expected_revision_id: id, reviewer_comment: comment || null } })
    if (result) onDecided(decision)
  }
  const asset = revision.agent_result?.output?.asset_tag
  return <article className="review-pane" aria-labelledby="review-title">
    <header className="review-head">
      <div><h2 id="review-title">{title(revision.route)}{asset && <> · <span className="identifier">{asset}</span></>}</h2>
        <p className="muted small">Revision <code className="identifier">{revision.action_revision_id.slice(0, 8)}</code> · policy {revision.policy_version || 'unreported'}</p></div>
      <div className="review-chips"><Chip tone={statusTone}>{statusLabel}</Chip><Chip tone={bindingTone}>{bindingLabel}</Chip></div>
    </header>
    <p className="review-scope"><Icon name="shield" size={16} />Approval releases this advisory recommendation only. No plant or equipment action exists here.</p>
    <Advisory revision={revision} />
    {!!revision.warnings?.length && <section className="advisory-block"><h4>Warnings</h4><ul className="warn-list">{revision.warnings.map((w, i) => <li key={i}>{typeof w === 'string' ? w : JSON.stringify(w)}</li>)}</ul></section>}
    <section className="advisory-block"><h4>Evidence <small>{revision.evidence?.length || 0} cited sources</small></h4><EvidenceCards items={revision.evidence} /></section>
    <details className="integrity"><summary>Integrity and hashes</summary>
      <dl className="kv mono">{[['Revision', revision.action_revision_id], ['Request', revision.request_id], ['Action', revision.action_id], ['Request hash', revision.canonical_request_hash], ['Proposal hash', revision.canonical_proposal_hash], ['Evidence manifest', revision.evidence_manifest_hash || 'Not bound'], ['Evidence binding', revision.evidence_binding_status]].map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v || '—'}</dd></div>)}</dl>
    </details>
    <section className="advisory-block"><h4>Decision history</h4>{revision.decisions?.length ? <ol className="timeline">{revision.decisions.map((d, i) => <li key={i}><b>{String(d.decision || d.type || 'decision').replaceAll('_', ' ')}</b> <span className="muted small">{d.decided_at ? new Date(d.decided_at).toLocaleString() : ''}</span>{d.reviewer_comment && <p>{d.reviewer_comment}</p>}</li>)}</ol> : <p className="muted small">No decisions recorded yet.</p>}</section>

    {reviewer && <div className="decision-bar" role="group" aria-label="Decision">
      {pending ? <>
        <label className="decision-comment"><span className="visually-hidden">Reviewer comment (optional, recorded in the audit chain)</span>
          <textarea rows={2} maxLength={2000} value={comment} placeholder="Comment for the audit chain (optional)" onChange={event => setComment(event.target.value)} /></label>
        <div className="decision-actions">
          <button type="button" className="danger" disabled={action.loading || own} onClick={() => decide('reject')}>Reject advisory</button>
          <button type="button" className="primary" disabled={action.loading || own || (unbound && !ack)} onClick={() => decide('approve')}>Approve advisory</button>
        </div>
        {unbound && <label className="check decision-ack"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />I reviewed the cited sources myself; this evidence is not integrity-bound.</label>}
        {own && <p className="decision-reason"><Icon name="lock" size={16} />You requested this revision. Self-approval is blocked by the server.</p>}
      </> : <div className="decision-actions">
        <p className="muted small">This revision is {statusLabel.toLowerCase()}; its decisions are recorded above.</p>
        {revision.governance_status === 'APPROVED' && <button type="button" className="danger" disabled={action.loading} onClick={() => decide('revoke')}>Revoke approval</button>}
      </div>}
      {action.error && <p className="api-error" role="alert">{action.error.message}</p>}
    </div>}
  </article>
}

export function ReviewDesk({ user }) {
  const queue = useResource('/approvals')
  const detail = useRequest()
  const { run } = detail
  const [selected, setSelected] = useState(null)
  const [reload, setReload] = useState(0)
  const [manual, setManual] = useState('')
  const [notice, setNotice] = useState('')
  const items = queue.data || []
  // The oldest waiting draft opens by default, so the desk is never an empty room.
  const activeId = selected ?? items[0]?.action_revision_id ?? null
  useEffect(() => { if (activeId) run(`/approvals/${encodeURIComponent(activeId)}`) }, [activeId, reload, run])
  const open = id => { setSelected(id); setNotice('') }
  function onKey(event) {
    if (!['ArrowDown', 'ArrowUp', 'j', 'k'].includes(event.key) || !items.length) return
    event.preventDefault()
    const index = Math.max(0, items.findIndex(item => item.action_revision_id === activeId))
    const next = items[Math.min(items.length - 1, Math.max(0, index + (event.key === 'ArrowDown' || event.key === 'j' ? 1 : -1)))]
    document.getElementById(`queue-${next.action_revision_id}`)?.focus()
    open(next.action_revision_id)
  }
  return <div className="desk">
    <aside className="desk-queue" aria-label="Review queue">
      <header><h2>Queue</h2><span className="count">{items.length}</span>
        <button type="button" className="icon-button ghost" onClick={queue.refresh} aria-label="Refresh queue" disabled={queue.loading}><Icon name="refresh" size={18} /></button></header>
      {queue.error ? <ErrorState title="Queue unavailable" message={queue.error.message} onRetry={queue.refresh} /> : !queue.data ? <LoadingState label="Loading queue…" />
        : items.length ? <ul className="queue-rows" onKeyDown={onKey}>{items.map(item => <li key={item.action_revision_id}>
          <button type="button" id={`queue-${item.action_revision_id}`} className="queue-row" aria-current={activeId === item.action_revision_id || undefined} onClick={() => open(item.action_revision_id)}>
            <span className="queue-row-title">{title(item.route)}</span>
            <span className="queue-row-meta"><code className="identifier">{item.action_revision_id.slice(0, 8)}</code><span>{ago(item.created_at)}</span></span>
          </button></li>)}</ul>
          : <EmptyState title="The queue is clear" message="New advisory drafts appear here for human review." />}
      {items.length > 1 && <p className="muted small desk-hint"><kbd>↑</kbd> <kbd>↓</kbd> or <kbd>J</kbd> <kbd>K</kbd> move through the queue</p>}
      <details className="desk-lookup"><summary>Open a decided revision</summary>
        <form onSubmit={event => { event.preventDefault(); if (manual.trim()) open(manual.trim()) }}>
          <label>Revision ID<input value={manual} onChange={event => setManual(event.target.value)} required pattern="[0-9a-fA-F\-]{36}" placeholder="Paste a revision ID" /></label>
          <button type="submit" disabled={!manual.trim()}>Open revision</button></form></details>
    </aside>
    <section className="desk-detail" aria-live="polite">
      {notice && <p className="desk-notice" role="status"><Icon name="check" size={18} />{notice}</p>}
      {detail.error ? <ErrorState title="Revision unavailable" message={detail.error.message} onRetry={() => setReload(n => n + 1)} />
        : !detail.data ? (activeId ? <LoadingState label="Loading revision…" /> : <EmptyState title="Nothing to review" message="Drafts that could influence operations appear here for a human decision." />)
        : <ReviewPane key={`${detail.data.action_revision_id}-${detail.data.governance_status}`} revision={detail.data} user={user}
          onDecided={decision => { setNotice(`Decision “${decision}” recorded in the audit chain.`); queue.refresh(); setReload(n => n + 1) }} />}
    </section>
  </div>
}
