import { useEffect, useState } from 'react'
import { Link, Outlet, useMatches } from 'react-router'
import { Icon, Logo } from '../../components/ui.jsx'
import { useBackendHealth } from '../../hooks/useBackendHealth.js'
import SubsurfaceCanvas from '../landing/SubsurfaceCanvas.jsx'
import '../../styles/auth.css'

// Only product facts; the live line reflects the real backend health probe.
const STORIES = {
  login: 'Know what nearby wells learned before the bit gets there.',
  signup: 'Every account here is local to your deployment.',
  recovery: 'Account recovery stays inside your deployment.',
}
const PROOF = [
  ['map', 'Offset wells', 'ranked by formation, depth and trajectory, not distance alone'],
  ['gauge', 'Hazard look-ahead', 'for the next 50 / 100 / 150 m with cited evidence'],
  ['check', 'Engineer review', 'on every advisory; nothing operates rig equipment'],
]

export default function AuthLayout() {
  const matches = useMatches()
  const handle = [...matches].reverse().find(match => match.handle?.authMedia)?.handle || {}
  const [paused, setPaused] = useState(false)
  const { status } = useBackendHealth()
  useEffect(() => { document.title = `${handle.title || 'Sign in'} · eRTMAC-NWIS` }, [handle.title])
  const online = status === 'Connected'

  return <div className="auth-shell" data-theme="dark" data-placement="upper" data-still={paused || undefined}>
    <div className="auth-media" aria-hidden="true">
      <div className="auth-layer"><SubsurfaceCanvas className="auth-scene" paused={paused} activeX={0.78} /></div>
      <div className="auth-grade" /><div className="auth-grain" />
    </div>
    <header className="auth-top">
      <Link to="/" className="auth-brand" aria-label="eRTMAC-NWIS home"><Logo variant="horizontal" decorative /></Link>
      <div className="auth-top-actions">
        <span className="auth-live" data-state={online ? 'ok' : status === 'Checking' ? 'pending' : 'bad'} role="status">
          <span className="auth-live-dot" aria-hidden="true" /><span className="auth-live-long">{online ? 'Backend online' : status === 'Checking' ? 'Checking backend…' : 'Backend unavailable'}</span><span className="auth-live-short" aria-hidden="true">{online ? 'Online' : status === 'Checking' ? 'Checking' : 'Offline'}</span></span>
        <button type="button" className="icon-button auth-pause" onClick={() => setPaused(value => !value)} aria-pressed={paused}
          aria-label={paused ? 'Play background animation' : 'Pause background animation'}><Icon name={paused ? 'play' : 'pause'} size={18} /></button>
      </div>
    </header>
    <main id="main" className="auth-stage">
      <section className="auth-story" aria-label="About eRTMAC-NWIS">
        <p className="auth-story-title" key={handle.authMedia}>{STORIES[handle.authMedia] || STORIES.login}</p>
        <p className="auth-story-lede">eRTMAC-NWIS, the Nearby Wells Intelligence System: AI-powered offset-well knowledge and decision support for drilling operations.</p>
        <ul className="auth-proof">{PROOF.map(([icon, figure, text]) => <li key={figure}><Icon name={icon} size={18} /><span><strong>{figure}</strong> {text}</span></li>)}</ul>
      </section>
      <div className="auth-card"><Outlet /></div>
    </main>
    <footer className="auth-foot">SIH26121 · Oil India Limited · Smart Automation · designed for Oil India / eRTMAC workflows · advisory decision support only</footer>
  </div>
}
