import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useSession } from '../../app/session.jsx'
import { safeNext } from '../../app/navigation.js'
import { useResource } from '../../hooks/useApi.js'
import { apiRequest } from '../../services/api.js'
import { Icon } from '../../components/ui.jsx'
import { capabilitiesFrom, normalizeEmail, passwordChecks, passwordValid, validateEmail, validateName, validateOtp } from './authModel.js'

// Self-service flows activate only when the backend reports the capability (planned account API).
function useAuthCapabilities() {
  const request = useResource('/auth/capabilities')
  return { ...capabilitiesFrom(request.data), loading: request.loading }
}

function AuthHeading({ title, children }) {
  return <div className="auth-heading"><h1 tabIndex={-1}>{title}</h1>{children && <p>{children}</p>}</div>
}

function Field({ label, error, hint, id, ...props }) {
  const describedBy = [error && `${id}-error`, hint && `${id}-hint`].filter(Boolean).join(' ') || undefined
  return <div className="field"><label htmlFor={id}>{label}</label>
    <input id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...props} />
    {hint && <p id={`${id}-hint`} className="hint">{hint}</p>}
    {error && <p id={`${id}-error`} className="field-error">{error}</p>}</div>
}

function PasswordField({ id, label, value, onChange, autoComplete, error }) {
  const [visible, setVisible] = useState(false)
  return <div className="field"><label htmlFor={id}>{label}</label>
    <div className="password-row"><input id={id} type={visible ? 'text' : 'password'} value={value} onChange={event => onChange(event.target.value)}
      autoComplete={autoComplete} required maxLength={255} aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : undefined} />
      <button type="button" className="ghost" onClick={() => setVisible(v => !v)} aria-pressed={visible}>{visible ? 'Hide' : 'Show'}</button></div>
    {error && <p id={`${id}-error`} className="field-error">{error}</p>}</div>
}

function PolicyChecklist({ password, context }) {
  return <ul className="policy-checklist" aria-label="Password requirements">{passwordChecks(password, context).map(check =>
    <li key={check.id} className={check.ok ? 'ok' : ''}><span aria-hidden="true">{check.ok ? '✓' : '•'}</span> {check.label}<span className="visually-hidden">{check.ok ? ' (met)' : ' (not met)'}</span></li>)}</ul>
}

function Notice({ children }) {
  return <div className="auth-notice" role="note"><Icon name="lock" size={18} /><p>{children}</p></div>
}

export function LoginPage() {
  const session = useSession()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (session.status === 'authenticated') return <Navigate to={next} replace />
  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      await session.signIn(username.trim(), password)
      navigate(next, { replace: true })
    } catch (failure) {
      setPassword('')
      setError(failure.status === 401 ? 'Incorrect username or password.' : failure.status === 429 ? 'Too many attempts. Wait and try again.' : failure.message)
    } finally { setBusy(false) }
  }
  return <>
    <AuthHeading title="Sign in">Local account on this Workbench. Your role is assigned by the server.</AuthHeading>
    {session.status === 'unavailable' && <Notice>The Workbench backend is not responding. Sign-in will work once it is available.</Notice>}
    <form onSubmit={submit}>
      <Field id="login-username" label="Username" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required maxLength={100} />
      <PasswordField id="login-password" label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
      {error && <p className="field-error" role="alert">{error}</p>}
      <button type="submit" className="primary" disabled={busy || !username.trim() || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
    <div className="auth-links"><Link to="/forgot-password">Forgot password?</Link><Link to="/signup">Create an account</Link></div>
  </>
}

export function SignUpPage() {
  const caps = useAuthCapabilities()
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [touched, setTouched] = useState(false)
  const [status, setStatus] = useState('')
  const set = key => event => setForm(value => ({ ...value, [key]: event.target.value }))
  const context = { email: form.email, name: form.name }
  const errors = { name: validateName(form.name), email: validateEmail(form.email),
    password: passwordValid(form.password, context) ? null : 'Meet every password requirement.',
    confirm: form.confirm === form.password ? null : 'Passwords do not match.' }
  async function submit(event) {
    event.preventDefault(); setTouched(true)
    if (!caps.signup || Object.values(errors).some(Boolean)) return
    try {
      await apiRequest('/auth/signup', { method: 'POST', body: { display_name: form.name.trim(), email: normalizeEmail(form.email), password: form.password } })
      setStatus(caps.signup_mode === 'approval' ? 'Request received. An administrator must approve your account before you can sign in.' : 'Account created. You can now sign in.')
    } catch (failure) { setStatus(failure.message) }
  }
  const signupForm = (
    <form onSubmit={submit}><fieldset disabled={!caps.signup}>
      <Field id="signup-name" label="Full name" value={form.name} onChange={set('name')} autoComplete="name" maxLength={100} required error={touched && errors.name} />
      <Field id="signup-email" label="Work email" type="email" value={form.email} onChange={set('email')} autoComplete="email" maxLength={254} required error={touched && errors.email} />
      <PasswordField id="signup-password" label="Password" value={form.password} onChange={value => setForm(v => ({ ...v, password: value }))} autoComplete="new-password" error={touched && errors.password} />
      <PolicyChecklist password={form.password} context={context} />
      <PasswordField id="signup-confirm" label="Confirm password" value={form.confirm} onChange={value => setForm(v => ({ ...v, confirm: value }))} autoComplete="new-password" error={touched && errors.confirm} />
      <button type="submit" className="primary">Create account</button>
    </fieldset></form>
  )
  return <>
    <AuthHeading title="Create an account">New accounts always start with the requester role. Reviewer and admin roles are granted only by an administrator.</AuthHeading>
    {!caps.loading && !caps.signup && <Notice>Self-service sign-up is not enabled on this Workbench. Ask your administrator to create an account for you.</Notice>}
    {/* Until the backend enables sign-up, the form stays a preview so nobody fills in fields that cannot be submitted. */}
    {caps.signup ? signupForm : <details className="auth-preview"><summary>Preview what sign-up will ask for</summary>{signupForm}</details>}
    {status && <p role="status">{status}</p>}
    <div className="auth-links"><Link to="/login">Already have an account? Sign in</Link></div>
  </>
}

export function ForgotPasswordPage() {
  const caps = useAuthCapabilities()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  async function submit(event) {
    event.preventDefault()
    if (!caps.email_recovery || validateEmail(email)) return
    try { await apiRequest('/auth/password/forgot', { method: 'POST', body: { email: normalizeEmail(email) } }) } catch { /* Same message either way. */ }
    setSent(true) // Never reveal whether an account exists.
  }
  return <>
    <AuthHeading title="Forgot your password?" />
    {!caps.loading && !caps.email_recovery && <Notice>Email recovery is not available on this Workbench. Contact your Workbench administrator for a one-time recovery code, then <Link to="/verify-otp">enter it here</Link>.</Notice>}
    {sent ? <p role="status">If an account exists for that address, a recovery code has been sent. It expires shortly.</p>
      : <form onSubmit={submit}><fieldset disabled={!caps.email_recovery}>
        <Field id="forgot-email" label="Work email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required />
        <button type="submit" className="primary">Send recovery code</button></fieldset></form>}
    <div className="auth-links"><Link to="/login">Back to sign in</Link></div>
  </>
}

export function VerifyOtpPage() {
  const caps = useAuthCapabilities()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const enabled = caps.email_recovery || caps.admin_recovery
  async function submit(event) {
    event.preventDefault()
    const problem = validateEmail(email) || validateOtp(code)
    if (!enabled || problem) { setError(problem || ''); return }
    try {
      const result = await apiRequest('/auth/password/verify-otp', { method: 'POST', body: { email: normalizeEmail(email), code } })
      navigate('/reset-password', { state: { token: result.reset_token } })
    } catch (failure) { setError(failure.status === 429 ? 'Too many attempts. Request a new code later.' : 'That code is invalid or has expired.') }
  }
  return <>
    <AuthHeading title="Enter your recovery code">Use the 6-digit code from your administrator or recovery email.</AuthHeading>
    {!caps.loading && !enabled && <Notice>Recovery codes are not enabled on this Workbench yet. Your administrator can reset your access.</Notice>}
    <form onSubmit={submit}><fieldset disabled={!enabled}>
      <Field id="otp-email" label="Work email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required />
      <Field id="otp-code" label="6-digit code" value={code} onChange={event => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
        inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} required hint="Codes expire and can be used once." />
      {error && <p className="field-error" role="alert">{error}</p>}
      <button type="submit" className="primary">Verify code</button></fieldset></form>
    <div className="auth-links"><Link to="/forgot-password">Need a code?</Link><Link to="/login">Back to sign in</Link></div>
  </>
}

export function ResetPasswordPage() {
  const caps = useAuthCapabilities()
  const location = useLocation()
  const token = location.state?.token
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const enabled = !!token && (caps.email_recovery || caps.admin_recovery)
  async function submit(event) {
    event.preventDefault()
    if (!enabled || !passwordValid(password) || password !== confirm) { setError('Meet every requirement and confirm the same password.'); return }
    try { await apiRequest('/auth/password/reset', { method: 'POST', body: { reset_token: token, new_password: password } }); setDone(true) }
    catch { setError('This reset link has expired or was already used. Request a new code.') }
  }
  return <>
    <AuthHeading title="Choose a new password" />
    {done ? <p role="status">Password updated. All your existing sessions were signed out. <Link to="/login">Sign in</Link></p> : <>
      {!enabled && !caps.loading && <Notice>Verify a recovery code first. <Link to="/verify-otp">Enter a code</Link></Notice>}
      <form onSubmit={submit}><fieldset disabled={!enabled}>
        <PasswordField id="reset-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" />
        <PolicyChecklist password={password} />
        <PasswordField id="reset-confirm" label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
        {error && <p className="field-error" role="alert">{error}</p>}
        <button type="submit" className="primary">Update password</button></fieldset></form></>}
  </>
}

export function OAuthCallbackPage() {
  const caps = useAuthCapabilities()
  return <>
    <AuthHeading title="Google sign-in" />
    {caps.loading ? <p role="status">Checking sign-in options…</p> : <Notice>Google sign-in is not enabled on this Workbench. Confidential and offline deployments use local accounts only.</Notice>}
    <div className="auth-links"><Link to="/login">Sign in with a local account</Link></div>
  </>
}
