import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useSession } from '../../app/session.jsx'
import { safeNext } from '../../app/navigation.js'
import { useAuthCapabilities } from '../../hooks/useApi.js'
import { API_BASE_URL, apiRequest } from '../../services/api.js'
import { Icon } from '../../components/ui.jsx'
import { normalizeEmail, passwordChecks, passwordValid, recoveryIdentifier, validateEmail, validateName, validateOtp } from './authModel.js'

function useSecondsUntil(deadline) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return Math.max(0, Math.ceil(((deadline || 0) - now) / 1000))
}

function GoogleSignIn({ enabled, next }) {
  if (!enabled) return null
  return <a className="primary" href={`${API_BASE_URL}/auth/google/start`} onClick={() => {
    try { sessionStorage.setItem('workbench-auth-next', safeNext(next)) } catch { /* Dashboard fallback. */ }
  }}>Continue with Google</a>
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
  const caps = useAuthCapabilities()
  const location = useLocation()
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
      setError(failure.status === 401 ? 'Incorrect email, username or password.' : failure.status === 429 ? 'Too many attempts. Wait and try again.' : failure.message)
    } finally { setBusy(false) }
  }
  return <>
    <AuthHeading title="Sign in">Local account on this Workbench. Your role is assigned by the server.</AuthHeading>
    {session.status === 'unavailable' && <Notice>The Workbench backend is not responding. Sign-in will work once it is available.</Notice>}
    {location.state?.passwordReset && <p role="status">Password updated. All existing sessions were signed out. Sign in with your new password.</p>}
    <form onSubmit={submit}>
      <Field id="login-username" label="Email or username" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required maxLength={254} />
      <PasswordField id="login-password" label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
      {error && <p className="field-error" role="alert">{error}</p>}
      <button type="submit" className="primary" disabled={busy || !username.trim() || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
    <GoogleSignIn enabled={caps.google} next={next} />
    <div className="auth-links"><Link to="/forgot-password">Forgot password?</Link><Link to="/signup">Create an account</Link></div>
  </>
}

export function SignUpPage() {
  const caps = useAuthCapabilities()
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [touched, setTouched] = useState(false)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const set = key => event => setForm(value => ({ ...value, [key]: event.target.value }))
  const context = { email: form.email, name: form.name }
  const errors = { name: validateName(form.name), email: validateEmail(form.email),
    password: passwordValid(form.password, context) ? null : 'Meet every password requirement.',
    confirm: form.confirm === form.password ? null : 'Passwords do not match.' }
  async function submit(event) {
    event.preventDefault(); setTouched(true)
    if (busy || !caps.signup || Object.values(errors).some(Boolean)) return
    setBusy(true); setStatus('')
    try {
      await apiRequest('/auth/signup', { method: 'POST', body: { display_name: form.name.trim(), email: normalizeEmail(form.email), password: form.password } })
      setStatus(caps.signup_mode === 'approval' ? 'Request received. Eligible new accounts require administrator approval before sign-in.' : 'Request received. If eligible, your account is ready for sign-in. If you already have an account, sign in or recover access.')
      setForm(value => ({ ...value, password: '', confirm: '' })); setTouched(false)
    } catch (failure) { setStatus(failure.message) }
    finally { setBusy(false) }
  }
  const signupForm = (
    <form onSubmit={submit}><fieldset disabled={!caps.signup || busy}>
      <Field id="signup-name" label="Full name" value={form.name} onChange={set('name')} autoComplete="name" maxLength={100} required error={touched && errors.name} />
      <Field id="signup-email" label="Work email" type="email" value={form.email} onChange={set('email')} autoComplete="email" maxLength={254} required error={touched && errors.email} />
      <PasswordField id="signup-password" label="Password" value={form.password} onChange={value => setForm(v => ({ ...v, password: value }))} autoComplete="new-password" error={touched && errors.password} />
      <PolicyChecklist password={form.password} context={context} />
      <PasswordField id="signup-confirm" label="Confirm password" value={form.confirm} onChange={value => setForm(v => ({ ...v, confirm: value }))} autoComplete="new-password" error={touched && errors.confirm} />
      <button type="submit" className="primary">{busy ? 'Submitting…' : 'Create account'}</button>
    </fieldset></form>
  )
  return <>
    <AuthHeading title="Create an account">New accounts always start with the requester role. Reviewer and admin roles are granted only by an administrator.</AuthHeading>
    {!caps.loading && !caps.signup && <Notice>Self-service sign-up is not enabled on this Workbench. Ask your administrator to create an account for you.</Notice>}
    {/* Until the backend enables sign-up, the form stays a preview so nobody fills in fields that cannot be submitted. */}
    {caps.signup ? signupForm : <details className="auth-preview"><summary>Preview what sign-up will ask for</summary>{signupForm}</details>}
    {status && <p role="status">{status}</p>}
    <GoogleSignIn enabled={caps.google} />
    <div className="auth-links"><Link to="/login">Already have an account? Sign in</Link></div>
  </>
}

export function ForgotPasswordPage() {
  const caps = useAuthCapabilities()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [resendAt, setResendAt] = useState(0)
  async function submit(event) {
    event.preventDefault()
    if (busy || !caps.email_recovery || validateEmail(email)) return
    setBusy(true); setError('')
    try {
      await apiRequest('/auth/password/forgot', { method: 'POST', body: { email: normalizeEmail(email) } })
      setResendAt(Date.now() + 60000); setSent(true)
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <>
    <AuthHeading title="Forgot your password?" />
    {!caps.loading && !caps.email_recovery && <Notice>Email recovery is not available on this Workbench. {caps.admin_recovery ? <>Contact your Workbench administrator for a one-time recovery code, then <Link to="/verify-otp">enter it here</Link> with your email or legacy username.</> : 'Contact your Workbench administrator to restore access.'}</Notice>}
    {sent ? <p role="status">If this address belongs to an eligible verified account, recovery instructions will be sent. Codes expire after 10 minutes. <Link to="/verify-otp" state={{ identifier: normalizeEmail(email), resendAt }}>Enter recovery code</Link></p>
      : <form onSubmit={submit}><fieldset disabled={!caps.email_recovery || busy}>
        <Field id="forgot-email" label="Work email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required />
        <button type="submit" className="primary">Send recovery code</button></fieldset></form>}
    {error && <p className="field-error" role="alert">{error}</p>}
    <div className="auth-links"><Link to="/login">Back to sign in</Link></div>
  </>
}

export function VerifyOtpPage() {
  const caps = useAuthCapabilities()
  const session = useSession()
  const location = useLocation()
  const navigate = useNavigate()
  const [email, setEmail] = useState(location.state?.identifier || '')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [resendAt, setResendAt] = useState(location.state?.resendAt || 0)
  const remaining = useSecondsUntil(resendAt)
  const enabled = caps.email_recovery || caps.admin_recovery
  async function submit(event) {
    event.preventDefault()
    const problem = !email.trim() ? 'Enter your email or username.' : (email.includes('@') && validateEmail(email)) || validateOtp(code)
    if (busy || !enabled || problem) { setError(problem || ''); return }
    setBusy(true); setError('')
    try {
      const result = await apiRequest('/auth/password/verify-otp', { method: 'POST', body: { ...recoveryIdentifier(email), code } })
      session.setRecovery({ token: result.reset_token, expiresAt: Date.now() + result.expires_in * 1000 })
      navigate('/reset-password', { replace: true })
    } catch (failure) { setError(failure.status === 429 ? 'Too many attempts. Request a new code later.' : failure.status === 400 ? 'That code is invalid or has expired.' : failure.message) }
    finally { setBusy(false) }
  }
  async function resend() {
    if (busy || remaining || !caps.email_recovery || validateEmail(email)) return
    setBusy(true); setError(''); setMessage('')
    try {
      await apiRequest('/auth/password/forgot', { method: 'POST', body: { email: normalizeEmail(email) } })
      setResendAt(Date.now() + 60000); setCode('')
      setMessage('If the account is eligible, a new code will be sent. Use the latest code within 10 minutes.')
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <>
    <AuthHeading title="Enter your recovery code">Use the 6-digit code from your administrator or recovery email.</AuthHeading>
    {!caps.loading && !enabled && <Notice>Recovery codes are not enabled on this Workbench yet. Your administrator can reset your access.</Notice>}
    <form onSubmit={submit}><fieldset disabled={!enabled || busy}>
      <Field id="otp-email" label="Email or username" value={email} onChange={event => setEmail(event.target.value)} autoComplete="username" maxLength={254} required />
      <Field id="otp-code" label="6-digit code" value={code} onChange={event => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
        inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} required hint="Codes expire and can be used once." />
      {error && <p className="field-error" role="alert">{error}</p>}
      <button type="submit" className="primary">Verify code</button></fieldset></form>
    {caps.email_recovery && <button type="button" onClick={resend} disabled={busy || remaining > 0 || !!validateEmail(email)}>{remaining ? `Resend in ${remaining}s` : 'Resend code'}</button>}
    {message && <p role="status">{message}</p>}
    <div className="auth-links"><Link to="/forgot-password">Need a code?</Link><Link to="/login">Back to sign in</Link></div>
  </>
}

export function ResetPasswordPage() {
  const caps = useAuthCapabilities()
  const session = useSession()
  const navigate = useNavigate()
  const grant = session.recovery
  const remaining = useSecondsUntil(grant?.expiresAt)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const enabled = !!grant?.token && remaining > 0 && (caps.email_recovery || caps.admin_recovery)
  async function submit(event) {
    event.preventDefault()
    if (busy || !enabled || !passwordValid(password) || password !== confirm) { setError('Meet every requirement and confirm the same password.'); return }
    setBusy(true); setError('')
    try {
      await apiRequest('/auth/password/reset', { method: 'POST', body: { reset_token: grant.token, new_password: password } })
      session.setRecovery(null)
      await session.reload()
      navigate('/login', { replace: true, state: { passwordReset: true } })
    } catch (failure) { setError(failure.status === 400 ? 'This reset link has expired or was already used. Request a new code.' : failure.message) }
    finally { setBusy(false) }
  }
  return <>
    <AuthHeading title="Choose a new password" />
      {!enabled && !caps.loading && <Notice>Verify a recovery code first. Reset access expires after 10 minutes or when this page is refreshed. <Link to="/verify-otp">Enter a code</Link></Notice>}
      <form onSubmit={submit}><fieldset disabled={!enabled || busy}>
        <PasswordField id="reset-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" />
        <PolicyChecklist password={password} />
        <PasswordField id="reset-confirm" label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
        {error && <p className="field-error" role="alert">{error}</p>}
        <button type="submit" className="primary">Update password</button></fieldset></form>
  </>
}

export function OAuthCallbackPage() {
  const caps = useAuthCapabilities()
  const { reload } = useSession()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const status = params.get('status')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!caps.google || status !== 'success') return
    let active = true
    reload().then(user => {
      if (!active) return
      if (!user) { setError('Sign-in could not be confirmed. Please try again.'); return }
      let next
      try { next = sessionStorage.getItem('workbench-auth-next'); sessionStorage.removeItem('workbench-auth-next') } catch { /* Dashboard fallback. */ }
      navigate(safeNext(next), { replace: true })
    })
    return () => { active = false }
  }, [caps.google, status, reload, navigate])
  return <>
    <AuthHeading title="Google sign-in" />
    {caps.loading ? <p role="status">Checking sign-in options…</p> : !caps.google ? <Notice>Google sign-in is not enabled on this Workbench. Confidential and offline deployments use local accounts only.</Notice>
      : <p role="status">{error || (status === 'success' ? 'Confirming your session…' : status === 'pending_or_inactive' ? 'Your account requires administrator approval or activation.' : 'Google sign-in could not be completed. Please try again.')}</p>}
    <div className="auth-links"><Link to="/login">Sign in with a local account</Link></div>
  </>
}
