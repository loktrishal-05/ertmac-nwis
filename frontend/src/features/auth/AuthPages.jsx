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

// Shown only when the backend reports Google sign-in as configured. The flow is a full-page redirect through the backend.
function GoogleSignIn({ enabled, next }) {
  if (!enabled) return null
  return <>
    <p className="auth-divider"><span>or</span></p>
    <a className="button google-button" href={`${API_BASE_URL}/auth/google/start`} onClick={() => {
      try { sessionStorage.setItem('workbench-auth-next', safeNext(next)) } catch { /* Dashboard fallback. */ }
    }}><svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>Continue with Google</a>
  </>
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

// Development deployments deliver codes to a local test inbox (Mailpit), never to Gmail or other real mailboxes. Say so,
// instead of implying the code went to the person's own address.
function DevInboxNotice({ delivery }) {
  if (delivery !== 'local') return null
  return <Notice>Development mail: codes are delivered to the local test inbox at <a href="http://127.0.0.1:8025" target="_blank" rel="noreferrer">127.0.0.1:8025</a>, not to Gmail or other real mailboxes. Real delivery needs SMTP settings in the backend (<code>infra/.env</code>).</Notice>
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
    <AuthHeading title="Sign in">Local account on this NWIS deployment. Your role is assigned by the server.</AuthHeading>
    {session.status === 'unavailable' && <Notice>The NWIS backend is not responding. Sign-in will work once it is available.</Notice>}
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

// After sign-up the backend emails a 6-digit code (when email delivery is configured). Verifying it proves ownership of the
// address, which password recovery requires. The account can already sign in when sign-up is open.
function VerifyEmailStep({ email, approval, delivery }) {
  const [code, setCode] = useState('')
  const [state, setState] = useState({ busy: false, error: '', done: false })
  const [resendAt, setResendAt] = useState(() => Date.now() + 60000)
  const wait = useSecondsUntil(resendAt)
  async function submit(event) {
    event.preventDefault()
    const invalid = validateOtp(code)
    if (invalid) { setState(value => ({ ...value, error: invalid })); return }
    setState({ busy: true, error: '', done: false })
    try {
      await apiRequest('/auth/email/verify', { method: 'POST', body: { email, code } })
      setState({ busy: false, error: '', done: true })
    } catch (failure) { setCode(''); setState({ busy: false, error: failure.status === 400 ? 'That code is invalid or has expired. Request a new one.' : failure.message, done: false }) }
  }
  async function resend() {
    try { await apiRequest('/auth/email/request-verification', { method: 'POST', body: { email } }); setResendAt(Date.now() + 60000) }
    catch (failure) { setState(value => ({ ...value, error: failure.message })) }
  }
  if (state.done) return <div role="status" className="auth-success"><p><strong>Email verified.</strong> {approval ? 'An administrator must still approve the account before sign-in.' : 'Your account is ready.'}</p>
    {!approval && <Link className="button primary" to="/login">Sign in</Link>}</div>
  return <form onSubmit={submit} aria-labelledby="verify-email-title">
    <p id="verify-email-title" role="status">{delivery === 'local' ? <>A 6-digit verification code for <strong>{email}</strong> was delivered to the development inbox.</> : <>We sent a 6-digit verification code to <strong>{email}</strong>.</>} It expires in 10 minutes.</p>
    <DevInboxNotice delivery={delivery} />
    <Field id="verify-email-code" label="Verification code" value={code} onChange={event => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
      inputMode="numeric" autoComplete="one-time-code" required error={state.error} />
    <button type="submit" className="primary" disabled={state.busy || code.length !== 6}>{state.busy ? 'Verifying…' : 'Verify email'}</button>
    <div className="auth-links"><button type="button" className="ghost" onClick={resend} disabled={wait > 0}>{wait > 0 ? `Resend code in ${wait}s` : 'Resend code'}</button>
      {!approval && <Link to="/login">Skip for now and sign in</Link>}</div>
  </form>
}

export function SignUpPage() {
  const caps = useAuthCapabilities()
  const [verify, setVerify] = useState(null)
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
      const email = normalizeEmail(form.email)
      await apiRequest('/auth/signup', { method: 'POST', body: { display_name: form.name.trim(), email, password: form.password } })
      if (caps.email_recovery) {
        // The backend answers generically (it never reveals whether an address already had an account); a code is only sent to a new, unverified one.
        await apiRequest('/auth/email/request-verification', { method: 'POST', body: { email } })
        setVerify({ email, approval: caps.signup_mode === 'approval', delivery: caps.email_delivery })
        return
      }
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
  if (verify) return <>
    <AuthHeading title="Verify your email">One last step: confirm the address you signed up with.</AuthHeading>
    <VerifyEmailStep email={verify.email} approval={verify.approval} delivery={verify.delivery} />
  </>
  return <>
    <AuthHeading title="Create an account">New accounts always start with the requester role. Reviewer and admin roles are granted only by an administrator.</AuthHeading>
    {!caps.loading && !caps.signup && <Notice>Self-service sign-up is not enabled on this NWIS deployment. Ask your administrator to create an account for you.</Notice>}
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
    {!caps.loading && !caps.email_recovery && <Notice>Email recovery is not available on this NWIS deployment. {caps.admin_recovery ? <>Contact your NWIS administrator for a one-time recovery code, then <Link to="/verify-otp">enter it here</Link> with your email or legacy username.</> : 'Contact your NWIS administrator to restore access.'}</Notice>}
    {sent && <DevInboxNotice delivery={caps.email_delivery} />}
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
    <DevInboxNotice delivery={caps.email_delivery} />
    {!caps.loading && !enabled && <Notice>Recovery codes are not enabled on this NWIS deployment yet. Your administrator can reset your access.</Notice>}
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
    {caps.loading ? <p role="status">Checking sign-in options…</p> : !caps.google ? <Notice>Google sign-in is not enabled on this NWIS deployment. Confidential and offline deployments use local accounts only.</Notice>
      : <p role="status">{error || (status === 'success' ? 'Confirming your session…' : status === 'pending_or_inactive' ? 'Your account requires administrator approval or activation.' : 'Google sign-in could not be completed. Please try again.')}</p>}
    <div className="auth-links"><Link to="/login">Sign in with a local account</Link></div>
  </>
}
