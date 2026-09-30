import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useSession } from '../../app/session.jsx'
import { PageHeader } from '../../components/ui.jsx'
import { ApiState, DataView } from '../../WorkspacePages.jsx'
import { LanguageSelector } from '../../ProductPages.jsx'
import { useAuthCapabilities, useRequest, useResource } from '../../hooks/useApi.js'

export function AdminPage() {
  const { user } = useSession()
  const caps = useAuthCapabilities()
  const [offset, setOffset] = useState(0)
  const [pending, setPending] = useState(false)
  const users = useResource(`/admin/users?offset=${offset}&limit=25${pending ? '&pending=true' : ''}`)
  const action = useRequest()
  const [recovery, setRecovery] = useState(null)
  const [form, setForm] = useState({ display_name: '', username: '', email: '', password: '', role: 'requester' })
  useEffect(() => {
    if (!recovery) return
    const timer = setTimeout(() => setRecovery(null), recovery.expires_in * 1000)
    return () => clearTimeout(timer)
  }, [recovery])
  async function mutate(id, operation, body) {
    setRecovery(null)
    const result = await action.run(`/admin/users/${id}/${operation}`, { method: 'POST', body })
    if (result) {
      if (operation === 'recovery') setRecovery(result)
      users.refresh()
      action.reset() // Recovery codes are only held in the temporary notice below.
    }
  }
  async function create(event) {
    event.preventDefault()
    const body = { ...form, display_name: form.display_name.trim() }
    for (const key of ['email', 'username']) {
      if (body[key].trim()) body[key] = body[key].trim()
      else delete body[key]
    }
    const result = await action.run('/admin/users', { method: 'POST', body })
    if (result) { setForm({ display_name: '', username: '', email: '', password: '', role: 'requester' }); action.reset(); users.refresh() }
  }
  return <><PageHeader title="Administration" />
    <section className="panel"><h2>Users</h2>
      <div className="toolbar"><label><input type="checkbox" checked={pending} onChange={event => { setPending(event.target.checked); setOffset(0) }} /> Pending approval only</label><button onClick={users.refresh}>Refresh</button></div>
      <ApiState request={users} empty="No users on this page." /><ApiState request={action} />
      {recovery && <div role="status"><p>One-time recovery code for {recovery.email || recovery.username}: <strong>{recovery.code}</strong>. Expires in 10 minutes. Share through your approved local channel; no email was sent.</p><button onClick={() => setRecovery(null)}>Dismiss code</button></div>}
      {!!users.data?.length && <div className="table-scroll" tabIndex={0} role="region" aria-label="Users"><table>
        <thead><tr><th>Account</th><th>Status</th><th>Role</th><th>Actions</th></tr></thead>
        <tbody>{users.data.map(account => <tr key={account.id}>
          <td>{account.display_name || account.username}<br /><span className="muted">{account.email || account.username}</span></td>
          <td>{account.signup_pending ? 'Pending approval' : account.is_active ? 'Active' : 'Inactive'}</td>
          <td><select aria-label={`Role for ${account.email || account.username}`} value={account.role} disabled={action.loading || account.id === user.id}
            onChange={event => mutate(account.id, 'role', { role: event.target.value })}>{['requester', 'reviewer', 'admin'].map(role => <option key={role}>{role}</option>)}</select></td>
          <td><div className="toolbar">
            {account.signup_pending ? <button disabled={action.loading} onClick={() => mutate(account.id, 'approve')}>Approve</button>
              : <button disabled={action.loading || account.id === user.id} onClick={() => mutate(account.id, account.is_active ? 'deactivate' : 'activate')}>{account.is_active ? 'Deactivate' : 'Activate'}</button>}
            <button disabled={action.loading} onClick={() => mutate(account.id, 'revoke-sessions')}>Revoke sessions</button>
            {caps.admin_recovery && <button disabled={action.loading} onClick={() => mutate(account.id, 'recovery')}>Issue recovery code</button>}
          </div></td>
        </tr>)}</tbody></table></div>}
      <div className="toolbar"><button disabled={offset === 0 || users.loading} onClick={() => setOffset(value => Math.max(0, value - 25))}>Previous</button><span>Page {offset / 25 + 1}</span><button disabled={users.loading || users.data?.length !== 25} onClick={() => setOffset(value => value + 25)}>Next</button></div>
    </section>
    <section className="panel"><h2>Create account</h2><form onSubmit={create}><fieldset disabled={action.loading}>
      {['display_name', 'username', 'email', 'password'].map(key => <label key={key}>{({ display_name: 'Full name', username: 'Username (or supply email)', email: 'Email (or supply username)', password: 'Initial password' })[key]}
        <input value={form[key]} onChange={event => setForm(value => ({ ...value, [key]: event.target.value }))} type={key === 'password' ? 'password' : key === 'email' ? 'email' : 'text'}
          autoComplete={key === 'password' ? 'new-password' : 'off'} required={['display_name', 'password'].includes(key)} maxLength={key === 'email' ? 254 : key === 'password' ? 128 : 100} minLength={key === 'password' ? 12 : undefined} /></label>)}
      <label>Role<select value={form.role} onChange={event => setForm(value => ({ ...value, role: event.target.value }))}>{['requester', 'reviewer', 'admin'].map(role => <option key={role}>{role}</option>)}</select></label>
      <p className="muted">Use 12–128 characters, avoiding common passwords and the account name or email.</p>
      <button className="primary" disabled={!form.username.trim() && !form.email.trim()}>Create account</button>
    </fieldset></form></section>
  </>
}

export function ProfilePage() {
  const session = useSession()
  const { user } = session
  const caps = useAuthCapabilities()
  const navigate = useNavigate()
  const sessions = useResource('/auth/sessions')
  const action = useRequest()
  const [code, setCode] = useState('')
  const [resendAt, setResendAt] = useState(0)
  const [now, setNow] = useState(Date.now)
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
  const remaining = Math.max(0, Math.ceil((resendAt - now) / 1000))
  async function revoke(id) {
    if (await action.run(id ? `/auth/sessions/${id}/revoke` : '/auth/sessions/revoke-all', { method: 'POST' })) {
      sessions.refresh()
      if (!await session.reload()) navigate('/login', { replace: true })
    }
  }
  async function verify(event) {
    event.preventDefault()
    if (await action.run('/auth/email/verify', { method: 'POST', body: { email: user.email, code } })) { setCode(''); await session.reload() }
  }
  return <><PageHeader title="Profile" />
    <section className="panel"><DataView value={{ username: user?.username, display_name: user?.display_name, email: user?.email,
      email_verified: !!user?.email_verified_at, linked_providers: user?.linked_identities || [], server_role: user?.role }} />
      <ApiState request={action} />{action.data?.message && <p role="status">{action.data.message}</p>}
      {caps.email_recovery && user?.email && !user.email_verified_at && <>
        <button disabled={action.loading || remaining > 0} onClick={async () => {
          if (await action.run('/auth/email/request-verification', { method: 'POST', body: { email: user.email } })) setResendAt(Date.now() + 60000)
        }}>{remaining ? `Resend in ${remaining}s` : 'Send email verification code'}</button>
        <form onSubmit={verify}><label>Email verification code<input value={code} onChange={event => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required maxLength={6} /></label><button disabled={action.loading}>Verify email</button></form>
      </>}
      <p className="muted">Roles are assigned by an administrator. <Link to="/forgot-password">Recover or reset your password</Link>.</p>
      <div className="toolbar"><LanguageSelector /><button onClick={async () => { if (await session.signOut()) navigate('/login', { replace: true }) }}>Sign out</button></div>
      {session.error && <p role="alert">Sign-out failed. {session.error.message}</p>}
    </section>
    <section className="panel"><h2>Active sessions</h2><ApiState request={sessions} />
      {sessions.data?.map(row => <div className="toolbar" key={row.id}><span>{row.current ? 'This session' : 'Other session'} · Created {new Date(row.created_at).toLocaleString()} · Expires {new Date(row.expires_at).toLocaleString()}</span><button disabled={action.loading} onClick={() => revoke(row.id)}>Revoke</button></div>)}
      <button disabled={action.loading} onClick={() => revoke()}>Sign out all sessions</button>
    </section>
  </>
}
