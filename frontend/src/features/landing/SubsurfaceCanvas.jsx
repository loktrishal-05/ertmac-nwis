import { useEffect, useRef } from 'react'
import { createSubsurface } from './subsurface.js'

// Decorative subsurface scene for the landing hero and auth backdrop. Reduced motion, Save-Data or a paused
// state draw one still frame; hidden tabs and off-screen canvases stop animating.
export default function SubsurfaceCanvas({ className = '', paused = false, activeX, apiRef }) {
  const canvas = useRef(null)
  useEffect(() => {
    const element = canvas.current
    if (!element) return undefined
    const still = paused || !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !!navigator.connection?.saveData
    const scene = createSubsurface(element, { still, activeX, maxDpr: window.innerWidth < 760 ? 1.4 : 1.75 })
    if (!scene) return undefined
    const host = element.parentElement
    const fit = () => { const rect = host.getBoundingClientRect(); scene.resize(Math.min(rect.width, 3840), Math.min(rect.height, 2400)) }
    const observer = new ResizeObserver(fit)
    observer.observe(host)
    fit()
    let visible = true
    const sync = () => (visible && !document.hidden ? scene.play() : scene.pause())
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
    io.observe(element)
    document.addEventListener('visibilitychange', sync)
    const onPointer = event => scene.setPointer((event.clientX / window.innerWidth) * 2 - 1)
    window.addEventListener('pointermove', onPointer, { passive: true })
    if (apiRef) apiRef.current = scene
    sync()
    return () => { observer.disconnect(); io.disconnect(); document.removeEventListener('visibilitychange', sync); window.removeEventListener('pointermove', onPointer); scene.destroy(); if (apiRef) apiRef.current = null }
  }, [paused, activeX, apiRef])
  return <canvas ref={canvas} className={className} aria-hidden="true" />
}
