import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Outlet, useMatches } from 'react-router'
import { authMediaSources, playbackMode, readMediaEnvironment } from './authModel.js'
import { Icon, Logo } from '../../components/ui.jsx'
import '../../styles/auth.css'

// Presentational backdrop: the poster always renders first; the video is decorative and silent.
export function AuthBackdrop({ media, mode, onFailed, videoRef }) {
  const [ready, setReady] = useState(false)
  const attach = useCallback(element => {
    if (videoRef) videoRef.current = element
    if (!element) return
    element.muted = true // React does not reflect `muted`; autoplay policies require it.
    element.defaultMuted = true
    element.play?.()?.catch?.(() => onFailed?.(true))
  }, [videoRef, onFailed])
  return <div className="auth-media" aria-hidden="true">
    <img className="auth-poster" src={media.poster} alt="" decoding="async" fetchPriority="high" />
    {mode === 'video' && <video key={media.video} ref={attach} className={`auth-video${ready ? ' is-ready' : ''}`}
      src={media.video} poster={media.poster} autoPlay muted loop playsInline preload="metadata" tabIndex={-1}
      disablePictureInPicture disableRemotePlayback onLoadedData={() => setReady(true)} onError={() => onFailed?.(true)} />}
    <div className="auth-vignette" /><div className="auth-gradient" />
  </div>
}

export default function AuthLayout() {
  const matches = useMatches()
  const handle = [...matches].reverse().find(match => match.handle?.authMedia)?.handle || {}
  const [env, setEnv] = useState(null) // Unknown until mounted: poster first, always.
  const [failed, setFailed] = useState(false)
  const [userPaused, setUserPaused] = useState(false)
  const video = useRef(null)
  const media = authMediaSources(handle.authMedia, env?.narrow)
  const mode = failed ? 'poster' : playbackMode(env)

  useEffect(() => { document.title = `${handle.title || 'Sign in'} · Sovereign AI Workbench` }, [handle.title])
  useEffect(() => {
    const update = () => setEnv(readMediaEnvironment())
    update()
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    query?.addEventListener?.('change', update)
    return () => query?.removeEventListener?.('change', update)
  }, [])
  // Pause in hidden tabs; resume only if the viewer did not pause it.
  useEffect(() => {
    const onVisibility = () => {
      const element = video.current
      if (!element) return
      if (document.hidden) element.pause()
      else if (!userPaused) element.play?.()?.catch?.(() => setFailed(true))
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [userPaused])
  function togglePause() {
    const element = video.current
    if (!element) return
    if (userPaused) { element.play?.()?.catch?.(() => setFailed(true)); setUserPaused(false) } else { element.pause(); setUserPaused(true) }
  }

  return <div className="auth-shell" data-theme="dark" data-placement={media.placement}>
    <AuthBackdrop media={media} mode={mode} videoRef={video} onFailed={setFailed} />
    <header className="auth-top">
      <Link to="/" className="auth-brand" aria-label="Sovereign AI Workbench home"><Logo variant="horizontal" decorative /></Link>
      {mode === 'video' && <button type="button" className="icon-button auth-pause" onClick={togglePause} aria-pressed={userPaused}
        aria-label={userPaused ? 'Play background video' : 'Pause background video'}><Icon name={userPaused ? 'play' : 'pause'} /></button>}
    </header>
    <main id="main" className="auth-stage"><div className="auth-card"><Outlet /></div></main>
    <footer className="auth-foot">On-premise · local accounts · advisory recommendations only</footer>
  </div>
}
