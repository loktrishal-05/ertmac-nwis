import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { SOURCES, canvasSize, createParticles, particlePosition, smoothstep } from './landingModel.js'
import { createHeroScene } from './heroScene.js'

const LOGO = '/brand/nwis-app-logo-256.webp'
const stillOnly = () => typeof window === 'undefined' || !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !!navigator.connection?.saveData

// First viewport signature: the approved NWIS symbol assembled from GPU particles over a subsurface grid.
// Reduced motion, Save-Data or no WebGL keep the still symbol; the page is fully readable either way.
export function HeroScene({ apiRef }) {
  const canvas = useRef(null)
  const [still, setStill] = useState(stillOnly)
  useEffect(() => {
    const element = canvas.current
    if (still || !element) return undefined
    let scene = null, disposed = false, visible = true
    const cleanups = []
    const image = new Image()
    image.decoding = 'async'
    image.src = LOGO
    image.onload = () => {
      if (disposed) return
      try { scene = createHeroScene(element, image, { particles: window.innerWidth < 760 ? 6500 : 16000 }) } catch { scene = null }
      if (!scene) { setStill(true); return }
      // Size from the hero section (never from the canvas itself) and clamp, so the drawing buffer can never run away.
      const host = element.parentElement
      const fit = () => { const rect = host.getBoundingClientRect(); scene.resize(Math.min(rect.width, 3840), Math.min(rect.height, 2400), Math.min(window.devicePixelRatio || 1, window.innerWidth < 760 ? 1.4 : 1.75)) }
      const observer = new ResizeObserver(fit)
      observer.observe(host)
      fit()
      const sync = () => (visible && !document.hidden ? scene.play() : scene.pause())
      const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
      io.observe(element)
      document.addEventListener('visibilitychange', sync)
      const onPointer = event => { const rect = element.getBoundingClientRect(); scene.setPointer(((event.clientX - rect.left) / rect.width) * 2 - 1, -(((event.clientY - rect.top) / rect.height) * 2 - 1)) }
      window.addEventListener('pointermove', onPointer, { passive: true })
      const assemble = { value: 0 }
      const tween = gsap.to(assemble, { value: 1, duration: 3.4, delay: 0.3, ease: 'power3.inOut', onUpdate: () => scene.setAssemble(assemble.value) })
      if (apiRef) apiRef.current = scene
      sync()
      cleanups.push(() => { observer.disconnect(); io.disconnect(); tween.kill(); document.removeEventListener('visibilitychange', sync); window.removeEventListener('pointermove', onPointer) })
    }
    return () => { disposed = true; cleanups.forEach(fn => fn()); scene?.destroy(); if (apiRef) apiRef.current = null }
  }, [still, apiRef])
  if (still) return <img className="hero-mark" src={LOGO} alt="" width="256" height="256" fetchPriority="high" />
  return <canvas ref={canvas} className="hero-canvas" aria-hidden="true" />
}

// Scroll-scrubbed 2D canvas: five coloured knowledge clusters, each a small constellation, converge and join into one ring
// around the NWIS memory core. `controllerRef.current.setProgress(0..1)` is driven by the section's ScrollTrigger.
export function ConvergenceCanvas({ controllerRef, coreRef, initialProgress = 1 }) {
  const canvas = useRef(null)
  useEffect(() => {
    const element = canvas.current
    const context = element?.getContext?.('2d')
    if (!context) return undefined
    const particles = createParticles()
    const ring = [...particles].sort((a, b) => a.ringAngle - b.ringAngle)
    const bySource = SOURCES.map((_, index) => particles.filter(p => p.source === index))
    let progress = initialProgress // 0 = scattered until the pinned scroll drives it; 1 (reduced motion) = converged
    let frame = 0
    let size = { dpr: 1, cssWidth: 1, cssHeight: 1 }
    const draw = () => {
      frame = 0
      const { cssWidth: w, cssHeight: h, dpr } = size
      const scale = Math.min(w, h) * 0.86 // clusters, labels and ring all fit inside the pinned viewport
      const cx = w / 2, cy = h * 0.56 // below the section title, so the top cluster stays readable
      const at = p => { const q = particlePosition(p, progress); return [cx + q.x * scale, cy + q.y * scale, q.t] }
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, w, h)
      const glow = context.createRadialGradient(cx, cy, 0, cx, cy, scale * 0.45)
      glow.addColorStop(0, `rgba(53, 215, 232, ${0.05 + 0.2 * progress})`)
      glow.addColorStop(1, 'rgba(2, 14, 33, 0)')
      context.fillStyle = glow
      context.fillRect(0, 0, w, h)
      context.globalCompositeOperation = 'lighter'
      // Constellation threads inside each cluster; they fade as the clusters leave home.
      const threads = 1 - smoothstep(0.1, 0.55, progress)
      if (threads > 0.01) bySource.forEach((group, index) => {
        context.strokeStyle = SOURCES[index].color
        context.globalAlpha = 0.22 * threads
        context.lineWidth = 0.8
        context.beginPath()
        for (let i = 0; i < group.length - 6; i += 3) { const [x1, y1] = at(group[i]), [x2, y2] = at(group[i + 5]); context.moveTo(x1, y1); context.lineTo(x2, y2) }
        context.stroke()
      })
      // As they arrive, neighbours on the ring join up: the dots become one continuous circle.
      const join = smoothstep(0.66, 0.95, progress)
      if (join > 0.01) {
        context.globalAlpha = 0.75 * join
        context.lineWidth = 1.4
        for (let i = 0; i < ring.length; i += 1) {
          const a = ring[i], b = ring[(i + 1) % ring.length]
          const [x1, y1] = at(a), [x2, y2] = at(b)
          context.strokeStyle = a.color
          context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2); context.stroke()
        }
      }
      for (const particle of particles) {
        const [x, y, t] = at(particle)
        context.globalAlpha = 0.35 + 0.6 * t
        context.fillStyle = particle.color
        context.beginPath()
        context.arc(x, y, particle.size * (1 + t * 0.5), 0, Math.PI * 2)
        context.fill()
      }
      context.globalCompositeOperation = 'source-over'
      // Source names at their clusters, fading out as they merge.
      context.globalAlpha = 1 - smoothstep(0.15, 0.5, progress)
      context.font = `600 ${Math.max(12, Math.round(scale * 0.022))}px system-ui, sans-serif`
      context.textAlign = 'center'
      SOURCES.forEach((source, index) => {
        const angle = (index / SOURCES.length) * Math.PI * 2 - Math.PI / 2
        context.fillStyle = source.color
        context.fillText(w < 640 ? source.short : source.label, cx + Math.cos(angle) * scale * 0.47, cy + Math.sin(angle) * scale * 0.47 + 4)
      })
      context.globalAlpha = 1
      // The HTML core (logo + words) sits inside the ring and fades in with it.
      if (coreRef?.current) coreRef.current.style.setProperty('--core', smoothstep(0.6, 0.95, progress).toFixed(3))
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw) }
    const resize = () => {
      const rect = element.getBoundingClientRect()
      const next = canvasSize(rect.width, rect.height, window.devicePixelRatio)
      element.width = next.width
      element.height = next.height
      size = { dpr: next.dpr, cssWidth: rect.width, cssHeight: rect.height }
      schedule()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    controllerRef.current = { setProgress: value => { if (value !== progress) { progress = value; schedule() } } }
    resize()
    return () => { observer.disconnect(); cancelAnimationFrame(frame); controllerRef.current = null }
  }, [controllerRef, coreRef, initialProgress])
  return <canvas ref={canvas} className="unify-canvas" role="img"
    aria-label="Daily drilling reports, well completion reports, formation tops, trajectory surveys and drilling telemetry converging into one NWIS offset-well memory" />
}

// Connectors from the NWIS core to every service in the architecture topology. Positions come from layout (offsetLeft/Top),
// which ignores the GSAP transforms that animate the nodes into place, so the lines always end where the nodes settle.
// The host is the SVG's own parent: a child's layout effect runs before the parent's ref is attached.
export function TopologyLinks() {
  const svg = useRef(null)
  const [lines, setLines] = useState({ w: 1, h: 1, items: [] })
  useLayoutEffect(() => {
    const host = svg.current?.parentElement
    if (!host) return undefined
    const measure = () => {
      const core = host.querySelector('.node.core')
      if (!core) return
      const c = [core.offsetLeft + core.offsetWidth / 2, core.offsetTop + core.offsetHeight / 2]
      const items = [...host.querySelectorAll('.node:not(.core)')].map(node => [node.offsetLeft + node.offsetWidth / 2, node.offsetTop + node.offsetHeight / 2])
      setLines({ w: host.clientWidth, h: host.clientHeight, c, items })
    }
    const observer = new ResizeObserver(measure)
    observer.observe(host)
    measure()
    return () => observer.disconnect()
  }, [])
  return <svg ref={svg} className="topo-links" viewBox={`0 0 ${lines.w} ${lines.h}`} preserveAspectRatio="none" aria-hidden="true">
    {lines.c && lines.items.map(([x, y], i) => <path key={i} className="topo-link" pathLength="1" d={`M${lines.c[0]} ${lines.c[1]} C ${lines.c[0]} ${(lines.c[1] + y) / 2}, ${x} ${(lines.c[1] + y) / 2}, ${x} ${y}`} />)}
  </svg>
}
