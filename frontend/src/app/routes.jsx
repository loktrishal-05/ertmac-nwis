import { Navigate } from 'react-router'
import { RequireAuth, RootLayout } from './session.jsx'
import { Forbidden, LoadingState, NotFound, RouteError } from '../components/ui.jsx'
import { ADMINS, REVIEWERS } from './navigation.js'

// Each area is a lazy chunk: landing (GSAP), auth (video), shell and pages load independently.
const lazyNamed = (loader, name) => async () => ({ Component: (await loader())[name] })
const pages = () => import('./AppPages.jsx')
const authPages = () => import('../features/auth/AuthPages.jsx')
const page = (path, name, title) => ({ path, lazy: lazyNamed(pages, name), handle: { title } })
const indexPage = (name, title) => ({ index: true, lazy: lazyNamed(pages, name), handle: { title } })
const authPage = (path, name, title, media) => ({ path, lazy: lazyNamed(authPages, name), handle: { title, authMedia: media } })

export const routes = [{
  id: 'root',
  element: <RootLayout />,
  errorElement: <RouteError />,
  hydrateFallbackElement: <LoadingState label="Loading Sovereign AI Workbench…" />,
  children: [
    { index: true, lazy: lazyNamed(() => import('../features/landing/LandingPage.jsx'), 'default'), handle: { title: 'Sovereign AI Workbench' } },
    {
      lazy: lazyNamed(() => import('../features/auth/AuthLayout.jsx'), 'default'),
      children: [
        authPage('login', 'LoginPage', 'Sign in', 'login'),
        authPage('signup', 'SignUpPage', 'Create account', 'signup'),
        authPage('forgot-password', 'ForgotPasswordPage', 'Forgot password', 'recovery'),
        authPage('verify-otp', 'VerifyOtpPage', 'Verify code', 'recovery'),
        authPage('reset-password', 'ResetPasswordPage', 'Reset password', 'recovery'),
        authPage('auth/callback', 'OAuthCallbackPage', 'Signing in', 'login'),
      ],
    },
    {
      path: 'app',
      element: <RequireAuth />,
      children: [{
        lazy: lazyNamed(() => import('./AppShell.jsx'), 'default'),
        children: [
          { index: true, element: <Navigate to="dashboard" replace /> },
          page('dashboard', 'DashboardPage', 'Dashboard'),
          page('workspace', 'WorkspacePage', 'AI Workspace'),
          page('workspace/voice', 'VoiceWorkspacePage', 'Voice query'),
          page('agents', 'AgentsPage', 'Agents'),
          page('pid', 'PidPage', 'P&ID Intelligence'),
          page('maintenance', 'MaintenancePage', 'Maintenance & Sensors'),
          { path: 'operations', children: [
            { index: true, element: <Navigate to="handover" replace /> },
            page(':view', 'OperationsPage', 'Operations'),
          ] },
          page('knowledge', 'KnowledgePage', 'Knowledge'),
          page('gaps', 'GapsPage', 'Knowledge Gaps'),
          page('approvals', 'ApprovalsPage', 'Approvals'),
          page('executions', 'ExecutionsPage', 'Executions'),
          { path: 'audit', element: <RequireAuth roles={REVIEWERS} />, children: [indexPage('AuditPage', 'Audit')] },
          page('sovereignty', 'SovereigntyPage', 'Sovereignty'),
          page('resources', 'ResourcesPage', 'Government Resources'),
          { path: 'admin', element: <RequireAuth roles={ADMINS} />, children: [
            indexPage('AdminPage', 'Administration'),
            page('*', 'AdminPage', 'Administration'),
          ] },
          page('profile', 'ProfilePage', 'Profile'),
          { path: '*', element: <NotFound />, handle: { title: 'Page not found' } },
        ],
      }],
    },
    { path: '403', element: <main id="main" className="standalone"><Forbidden /></main>, handle: { title: 'Access restricted' } },
    { path: '*', element: <main id="main" className="standalone"><NotFound /></main>, handle: { title: 'Page not found' } },
  ],
}]
