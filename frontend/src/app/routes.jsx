import { Navigate } from 'react-router'
import { RequireAuth, RootLayout } from './session.jsx'
import { Forbidden, LoadingState, NotFound, RouteError } from '../components/ui.jsx'
import { ADMINS, REVIEWERS } from './navigation.js'

// Each area is a lazy chunk: landing, auth, shell, NWIS pages and legacy pages load independently.
const lazyNamed = (loader, name) => async () => ({ Component: (await loader())[name] })
const nwis = () => import('../features/nwis/NwisPages.js')
const legacy = () => import('./AppPages.jsx')
const authPages = () => import('../features/auth/AuthPages.jsx')
const page = (path, name, title) => ({ path, lazy: lazyNamed(nwis, name), handle: { title } })
// Legacy SIH26117 screens: still routable (regression/tests), hidden from navigation and flagged in the shell.
const legacyPage = (path, name, title) => ({ path, lazy: lazyNamed(legacy, name), handle: { title, legacy: true } })
const authPage = (path, name, title, media) => ({ path, lazy: lazyNamed(authPages, name), handle: { title, authMedia: media } })

export const routes = [{
  id: 'root',
  element: <RootLayout />,
  errorElement: <RouteError />,
  hydrateFallbackElement: <LoadingState brand label="Loading eRTMAC-NWIS…" />,
  children: [
    { index: true, lazy: lazyNamed(() => import('../features/landing/LandingPage.jsx'), 'default'), handle: { title: 'eRTMAC-NWIS' } },
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
          page('map', 'MapPage', 'Nearby Wells Map'),
          page('wells', 'WellsPage', 'Well Catalogue'),
          page('wells/:id', 'WellCockpitPage', 'Well'),
          page('active', 'ActiveWellRedirect', 'Active Well'),
          page('offset-analysis', 'OffsetAnalysisPage', 'Offset Analysis'),
          page('correlation', 'CorrelationPage', 'Formation Correlation'),
          page('events', 'EventsPage', 'Drilling Events'),
          page('risk', 'RiskPage', 'Risk Look-Ahead'),
          page('live', 'LivePage', 'Live Drilling'),
          page('knowledge', 'KnowledgeSearchPage', 'Knowledge Search'),
          page('advisories', 'AdvisoriesPage', 'Advisories'),
          { path: 'audit', element: <RequireAuth roles={REVIEWERS} />, children: [{ index: true, lazy: lazyNamed(nwis, 'NwisAuditPage'), handle: { title: 'Audit' } }] },
          page('help', 'HelpPage', 'Help & Resources'),
          legacyPage('workspace', 'WorkspacePage', 'AI Workspace (legacy)'),
          legacyPage('workspace/voice', 'VoiceWorkspacePage', 'Voice query (legacy)'),
          legacyPage('agents', 'AgentsPage', 'Agents (legacy)'),
          legacyPage('pid', 'PidPage', 'Drawing viewer (legacy)'),
          legacyPage('maintenance', 'MaintenancePage', 'Sensors (legacy)'),
          { path: 'operations', handle: { legacy: true }, children: [
            { index: true, element: <Navigate to="handover" replace /> },
            legacyPage(':view', 'OperationsPage', 'Operations (legacy)'),
          ] },
          legacyPage('gaps', 'GapsPage', 'Knowledge Gaps (legacy)'),
          legacyPage('approvals', 'ApprovalsPage', 'Approvals (legacy)'),
          legacyPage('executions', 'ExecutionsPage', 'Executions (legacy)'),
          legacyPage('sovereignty', 'SovereigntyPage', 'Sovereignty (legacy)'),
          legacyPage('resources', 'ResourcesPage', 'Resources (legacy)'),
          { path: 'admin', element: <RequireAuth roles={ADMINS} />, children: [
            { index: true, lazy: lazyNamed(legacy, 'AdminPage'), handle: { title: 'Administration' } },
            { path: '*', lazy: lazyNamed(legacy, 'AdminPage'), handle: { title: 'Administration' } },
          ] },
          { path: 'profile', lazy: lazyNamed(legacy, 'ProfilePage'), handle: { title: 'Profile' } },
          { path: '*', element: <NotFound />, handle: { title: 'Page not found' } },
        ],
      }],
    },
    { path: '403', element: <main id="main" className="standalone"><Forbidden /></main>, handle: { title: 'Access restricted' } },
    { path: '*', element: <main id="main" className="standalone"><NotFound /></main>, handle: { title: 'Page not found' } },
  ],
}]
