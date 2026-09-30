import { useEffect, useRef } from 'react'

// Decorative looping film (muted, no controls, hidden from assistive tech). The poster shows first; the file is only
// requested once the element is on screen, plays while visible and pauses off screen, in hidden tabs or when `paused`.
// `still` (reduced motion, Save-Data, slow network) renders the poster image only.
export default function AmbientVideo({ src, poster, className = '', still = false, paused = false, eager = false }) {
  const video = useRef(null)
  useEffect(() => {
    const element = video.current
    if (!element) return undefined
    let visible = false
    const sync = () => {
      if (visible && !paused && !document.hidden) {
        if (!element.getAttribute('src')) element.setAttribute('src', src)
        element.play().catch(() => {}) // Autoplay refusal keeps the poster; nothing depends on playback.
      } else element.pause()
    }
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() }, { threshold: 0.15 })
    io.observe(element)
    document.addEventListener('visibilitychange', sync)
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', sync); element.pause() }
  }, [src, paused])
  if (still) return <img className={className} src={poster} alt="" decoding="async" loading={eager ? 'eager' : 'lazy'} fetchPriority={eager ? 'high' : 'auto'} />
  return <video ref={video} className={className} poster={poster} muted loop playsInline preload="none" aria-hidden="true" tabIndex={-1}
    disablePictureInPicture disableRemotePlayback />
}
