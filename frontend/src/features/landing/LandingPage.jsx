import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import { useGSAP } from '@gsap/react'
import { useSession } from '../../app/session.jsx'
import { Logo } from '../../components/ui.jsx'
import { PRODUCT_FACTS as F, SOURCES, STORY, canvasSize, createParticles, particlePosition, smoothstep } from './landingModel.js'
import { createHeroScene } from './heroScene.js'
import { createAtmosphere } from './atmosphere.js'
import './landing.css'

// Scroll-scrubbed canvas: five evidence clusters converge into the sovereign core. No video, no WebGL.
function ConvergenceCanvas({ controllerRef }) {
  const canvas = useRef(null)
  useEffect(() => {
    const element = canvas.current
    const context = element?.getContext?.('2d')
    if (!context) return undefined
    const particles = createParticles()
    const mark = new Image()
    mark.src = '/assets/branding/sovereign-mark.png'
    let progress = 1
    let frame = 0
    let size = { width: 1, height: 1, dpr: 1, cssWidth: 1, cssHeight: 1 }
    const draw = () => {
      frame = 0
      const { cssWidth: w, cssHeight: h, dpr } = size
      const scale = Math.min(w, h)
      const cx = w / 2
      const cy = h / 2
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, w, h)
      const glow = context.createRadialGradient(cx, cy, 0, cx, cy, scale * 0.42)
      glow.addColorStop(0, `rgba(53, 215, 232, ${0.06 + 0.22 * progress})`)
      glow.addColorStop(1, 'rgba(2, 14, 33, 0)')
      context.fillStyle = glow
      context.fillRect(0, 0, w, h)
      context.globalCompositeOperation = 'lighter'
      for (const particle of particles) {
        const position = particlePosition(particle, progress)
        context.globalAlpha = 0.3 + 0.6 * position.t
        context.fillStyle = particle.color
        context.beginPath()
        context.arc(cx + position.x * scale, cy + position.y * scale, particle.size * (1 + position.t * 0.5), 0, Math.PI * 2)
        context.fill()
      }
      context.globalAlpha = smoothstep(0.5, 0.85, progress)
      context.strokeStyle = 'rgba(53, 215, 232, 0.9)'
      context.lineWidth = 1.5
      context.beginPath()
      context.arc(cx, cy, scale * 0.16, 0, Math.PI * 2)
      context.stroke()
      if (mark.complete && mark.naturalWidth) {
        // Additive blending hides the mark's baked navy background on the dark canvas.
        context.globalAlpha = smoothstep(0.62, 0.95, progress)
        const markSize = scale * 0.25
        context.drawImage(mark, cx - markSize / 2, cy - markSize / 2, markSize, markSize)
      }
      context.globalCompositeOperation = 'source-over'
      context.globalAlpha = 1 - smoothstep(0.15, 0.5, progress)
      context.fillStyle = '#dbe7f6'
      context.font = `600 ${Math.max(12, Math.round(scale * 0.024))}px system-ui, sans-serif`
      context.textAlign = 'center'
      SOURCES.forEach((source, index) => {
        const angle = (index / SOURCES.length) * Math.PI * 2 - Math.PI / 2
        context.fillText(source.label, cx + Math.cos(angle) * scale * 0.46, cy + Math.sin(angle) * scale * 0.46)
      })
      context.globalAlpha = 1
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw) }
    const resize = () => {
      const rect = element.getBoundingClientRect()
      const next = canvasSize(rect.width, rect.height, window.devicePixelRatio)
      element.width = next.width
      element.height = next.height
      size = { ...next, cssWidth: rect.width, cssHeight: rect.height }
      schedule()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    mark.onload = schedule
    controllerRef.current = { setProgress: value => { if (value !== progress) { progress = value; schedule() } } }
    resize()
    return () => { observer.disconnect(); cancelAnimationFrame(frame); controllerRef.current = null }
  }, [controllerRef])
  return <canvas ref={canvas} className="unify-canvas" role="img" aria-label="SOPs, P&IDs, sensors, maintenance and operator knowledge converging into one sovereign intelligence core" />
}

// The first viewport's signature: the approved mark assembled from GPU particles over a P&ID-style floor.
// Reduced motion, Save-Data or no WebGL keep the still mark; the page is fully readable either way.
const stillOnly = () => typeof window === 'undefined' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !!navigator.connection?.saveData
function HeroScene({ apiRef }) {
  const canvas = useRef(null)
  const [still, setStill] = useState(stillOnly)
  useEffect(() => {
    const element = canvas.current
    if (still || !element) return undefined
    let scene = null, disposed = false, visible = true
    const cleanups = []
    const image = new Image()
    image.decoding = 'async'
    image.src = '/assets/branding/sovereign-mark.png'
    image.onload = () => {
      if (disposed) return
      try { scene = createHeroScene(element, image, { particles: window.innerWidth < 760 ? 6500 : 15000 }) } catch { scene = null }
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
      const tween = gsap.to(assemble, { value: 1, duration: 3.2, delay: 0.25, ease: 'power3.inOut', onUpdate: () => scene.setAssemble(assemble.value) })
      apiRef.current = scene
      sync()
      cleanups.push(() => { observer.disconnect(); io.disconnect(); tween.kill(); document.removeEventListener('visibilitychange', sync); window.removeEventListener('pointermove', onPointer) })
    }
    return () => { disposed = true; cleanups.forEach(fn => fn()); scene?.destroy(); apiRef.current = null }
  }, [still, apiRef])
  if (still) return <img className="hero-mark" src="/assets/branding/sovereign-mark.png" alt="" width="458" height="458" fetchPriority="high" />
  return <canvas ref={canvas} className="hero-canvas" aria-hidden="true" />
}

// One fixed backdrop for the whole page: smoke and beams that follow the cursor, from the hero to the footer.
// Reduced motion draws a single still frame; Save-Data or no WebGL keep the CSS gradient.
function Atmosphere() {
  const canvas = useRef(null)
  useEffect(() => {
    const element = canvas.current
    if (!element || navigator.connection?.saveData) return undefined
    const scene = createAtmosphere(element, { still: !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches })
    if (!scene) { element.hidden = true; return undefined }
    const sync = () => (document.hidden ? scene.pause() : scene.play())
    window.addEventListener('resize', scene.resize)
    document.addEventListener('visibilitychange', sync)
    sync()
    return () => { window.removeEventListener('resize', scene.resize); document.removeEventListener('visibilitychange', sync); scene.destroy() }
  }, [])
  return <canvas ref={canvas} className="atmosphere" aria-hidden="true" />
}

// Glass panels lean toward the cursor, drift a few pixels after it and catch light on the edge nearest to it.
function useMagneticGlass(root) {
  useEffect(() => {
    if (stillOnly() || !window.matchMedia?.('(hover: hover) and (pointer: fine)').matches) return undefined
    const cards = [...root.current.querySelectorAll('[data-glass]')]
    const move = event => {
      const card = event.currentTarget, rect = card.getBoundingClientRect()
      const x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height
      const tilt = Math.min(8, 2400 / Math.max(rect.width, rect.height)) // big panels tilt less
      card.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`)
      card.style.setProperty('--my', `${(y * 100).toFixed(1)}%`)
      card.style.rotate = `${(0.5 - y).toFixed(3)} ${(x - 0.5).toFixed(3)} 0 ${(Math.hypot(x - 0.5, y - 0.5) * tilt * 2).toFixed(2)}deg`
      card.style.translate = `${((x - 0.5) * 12).toFixed(1)}px ${((y - 0.5) * 12).toFixed(1)}px`
    }
    const leave = event => { event.currentTarget.style.rotate = ''; event.currentTarget.style.translate = '' }
    cards.forEach(card => { card.addEventListener('pointermove', move); card.addEventListener('pointerleave', leave) })
    return () => cards.forEach(card => { card.removeEventListener('pointermove', move); card.removeEventListener('pointerleave', leave); leave({ currentTarget: card }) })
  }, [root])
}

const Tag = ({ id }) => {
  const [code, number] = STORY.find(item => item.id === id).tag.split('-')
  return <span className="tag-bubble" aria-hidden="true"><span>{code}</span><span>{number}</span></span>
}

const Count = ({ value }) => <span className="fact-num" data-count={value}>{value.toLocaleString()}</span>

function SourceCard({ source, children }) {
  return <article className="source-card" data-glass style={{ '--accent': source.color }}><header><span className="dot" />{source.label}</header>{children}<footer>{source.detail}</footer></article>
}

const STATIONS = [
  ['Retrieve', 'Hybrid dense and sparse retrieval with reranking over your locally indexed documents. Every claim carries a citation.'],
  ['Verify', 'Evidence sufficiency and integrity checks. Verified knowledge is human-approved and goes stale when its source changes.'],
  ['Reason', `Risk-aware routing: bounded low-risk tasks may use ${F.fastModel}; safety and evidence-heavy reasoning uses ${F.primaryModel}.`],
  ['Review', 'Anything that could influence operations is held as a draft for a human reviewer. Self-approval is blocked.'],
  ['Approve', 'Approval releases advisory output only. No plant or equipment action is ever executed.'],
]

const ECOSYSTEM = [
  ['AIKosh', 'Resource registry', 'Downloadable resources need provenance, licence, a named approver and a pinned SHA-256 before local approval.'],
  ['BHASHINI', 'Public data only', 'Optional and off by default. Never used for confidential data; no client ships in this build.'],
  ['data.gov.in', 'Optional public connector', 'Off by default and never receives plant or company data.'],
  ['API Setu', 'Interface-ready', 'A registered-endpoint interface. No live integration is claimed.'],
  ['DigiLocker', 'Evaluated · future', 'Not part of confidential inference.'],
]

export default function LandingPage() {
  const root = useRef(null)
  const convergence = useRef(null)
  const heroScene = useRef(null)
  const session = useSession()
  const enter = session.status === 'authenticated' ? '/app/dashboard' : '/login'

  useMagneticGlass(root)
  useEffect(() => { document.title = 'Sovereign AI Workbench · Governed industrial intelligence on your own infrastructure' }, [])

  useGSAP(() => {
    gsap.registerPlugin(ScrollTrigger, SplitText)
    const mm = gsap.matchMedia()
    mm.add({ motion: '(prefers-reduced-motion: no-preference)', desktop: '(min-width: 1024px)' }, ({ conditions }) => {
      const { motion, desktop } = conditions
      if (!motion) { convergence.current?.setProgress(1); return undefined }
      root.current.classList.add('motion')
      root.current.style.setProperty('--flow', '0')
      // The rail carries pulses of light that stream down as the visitor scrolls and flare with scroll speed.
      const spine = root.current.querySelector('.spine')
      if (spine) ScrollTrigger.create({ trigger: root.current, start: 'top top', end: 'bottom bottom', onUpdate: self => {
        spine.style.setProperty('--off', (-window.scrollY / window.innerHeight * 0.35).toFixed(4))
        gsap.to(spine, { '--energy': Math.min(1, Math.abs(self.getVelocity()) / 2500), duration: 0.2, overwrite: true })
        gsap.to(spine, { '--energy': 0, duration: 1.4, delay: 0.25, ease: 'power2.out' })
      } })
      // Section headlines resolve word by word out of a blur, like an instrument coming into focus.
      gsap.utils.toArray('.story h2').forEach(heading => {
        const split = SplitText.create(heading, { type: 'words', wordsClass: 'word' })
        gsap.from(split.words, { opacity: 0, filter: 'blur(14px)', yPercent: 35, duration: 1.1, stagger: 0.07, ease: 'expo.out', clearProps: 'filter',
          scrollTrigger: { trigger: heading, start: 'top 88%', once: true } })
      })
      gsap.from('.hero-title .line', { yPercent: 105, duration: 1.3, stagger: 0.12, delay: 0.35, ease: 'expo.out' })
      gsap.from('.hero-copy > :not(h1)', { y: 24, opacity: 0, filter: 'blur(8px)', duration: 1.1, stagger: 0.1, delay: 0.75, ease: 'expo.out', clearProps: 'filter' })
      gsap.from('.hero-ghost', { opacity: 0, letterSpacing: '0.2em', duration: 2.4, ease: 'expo.out' })
      if (root.current.querySelector('.hero-mark')) gsap.to('.hero-mark', { yPercent: 22, ease: 'none', scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true } })
      ScrollTrigger.create({ trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true, onUpdate: self => heroScene.current?.setScroll(self.progress) })
      gsap.to('.hero-copy', { yPercent: -14, opacity: 0.15, ease: 'none', scrollTrigger: { trigger: '#hero', start: '30% top', end: 'bottom top', scrub: true } })
      gsap.to('.hero-ghost', { xPercent: -8, ease: 'none', scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true } })
      gsap.utils.toArray('[data-reveal]').forEach(element => gsap.from(element, { y: 36, opacity: 0, filter: 'blur(10px)', duration: 1, ease: 'expo.out', clearProps: 'filter',
        scrollTrigger: { trigger: element, start: 'top 85%', once: true } }))
      gsap.utils.toArray('[data-count]').filter(element => Number(element.dataset.count) >= 10).forEach(element => {
        // The true value shows until the count begins; a verified fact never reads as 0 while waiting.
        ScrollTrigger.create({ trigger: element, start: 'top 95%', once: true, onEnter: () => {
          const counter = { value: 0 }
          gsap.to(counter, { value: Number(element.dataset.count), duration: 1.6, ease: 'power1.out',
            onUpdate: () => { element.textContent = Math.round(counter.value).toLocaleString() } })
        } })
      })
      const offsets = [[-70, -45, -7], [60, -25, 6], [-35, 40, -4], [80, 45, 7], [-55, 15, -3]]
      // Full-width cards on narrow screens scatter vertically only, so they are never clipped at the edge.
      gsap.to('.source-card', { x: i => (desktop ? offsets[i][0] * 2 : 0), y: i => offsets[i][1] * (desktop ? 2 : 1), rotate: i => offsets[i][2] * (desktop ? 1 : 0.5), ease: 'none',
        scrollTrigger: { trigger: '#scattered', start: desktop ? 'top top' : 'top 60%', end: desktop ? '+=120%' : 'bottom top', scrub: true, pin: desktop ? '#scattered' : false } })
      const unify = gsap.timeline({ scrollTrigger: { trigger: '#unify', start: 'top top', end: desktop ? '+=220%' : '+=140%', pin: true, scrub: 0.6,
        onUpdate: self => convergence.current?.setProgress(self.progress) } })
      unify.to({}, { duration: 1 }, 0)
        .fromTo('.unify-note-a', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.1 }, 0.2)
        .to('.unify-note-a', { opacity: 0, duration: 0.08 }, 0.46)
        .fromTo('.unify-note-b', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.1 }, 0.62)
      convergence.current?.setProgress(0)
      const stations = gsap.utils.toArray('.station')
      ScrollTrigger.create({ trigger: '#workflow', start: 'top top', end: desktop ? '+=250%' : 'bottom center', pin: desktop,
        onUpdate: self => {
          const active = Math.min(stations.length - 1, Math.floor(self.progress * stations.length))
          stations.forEach((station, index) => station.classList.toggle('is-active', index <= active))
          root.current?.style.setProperty('--flow', self.progress.toFixed(3))
        } })
      gsap.fromTo('.reveal-frame', { rotateX: 28, scale: 0.86, y: 60 }, { rotateX: 0, scale: 1, y: 0, ease: 'none',
        scrollTrigger: { trigger: '#reveal', start: 'top bottom', end: 'center center', scrub: true } })
      gsap.utils.toArray('.draw').forEach(path => gsap.fromTo(path, { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: 'none',
        scrollTrigger: { trigger: path.closest('section'), start: 'top 70%', end: 'center 45%', scrub: true } }))
      const element = root.current
      return () => element?.classList.remove('motion')
    })
  }, { scope: root })

  return <div className="landing" data-theme="dark" ref={root}>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="landing-header">
      <Link to="/" aria-label="Sovereign AI Workbench home"><Logo variant="horizontal" decorative className="landing-logo" /></Link>
      <nav aria-label="Story"><a href="#workflow">Workflow</a><a href="#governance">Governance</a><a href="#sovereignty">Sovereignty</a><a href="#ecosystem">Ecosystem</a></nav>
      <Link className="button primary" to={enter}>{session.status === 'authenticated' ? 'Open Workbench' : 'Sign in'}</Link>
    </header>
    <Atmosphere />
    <svg className="spine" viewBox="0 0 24 1000" preserveAspectRatio="none" aria-hidden="true">
      <path className="spine-track" d="M12 0 V1000" />
      <path className="spine-glow" d="M12 0 V1000" pathLength="1" />
      <path className="spine-light" d="M12 0 V1000" pathLength="1" />
    </svg>
    <main id="main">
      <section id="hero" className="hero">
        <Tag id="hero" />
        <p className="hero-ghost" aria-hidden="true">Sovereign</p>
        <HeroScene apiRef={heroScene} />
        <div className="hero-scrim" aria-hidden="true" />
        <div className="hero-copy">
          <h1 className="hero-title"><span className="line-mask"><span className="line">Industrial intelligence</span></span> <span className="line-mask"><span className="line">that runs inside <em>your plant.</em></span></span></h1>
          <p className="lede">Sovereign AI Workbench answers from your procedures, drawings, sensors and maintenance history. Every answer cites its evidence, and every operational recommendation waits for a human.</p>
          <div className="hero-actions"><Link className="button primary" to={enter}>{session.status === 'authenticated' ? 'Open the Workbench' : 'Enter the Workbench'}</Link><a className="button ghost" href="#scattered">See how it works</a></div>
          <p className="hero-facts" aria-label="Verified product facts">
            <span><Count value={F.hostedAiCalls} /> hosted AI calls in the confidential path</span>
            <span><Count value={F.localModels} /> local models</span>
            <span><Count value={F.languages} /> languages · English, हिन्दी, தமிழ்</span>
            <span><Count value={F.backendTests} /> backend tests ({F.asOf})</span>
          </p>
        </div>
        <a className="scroll-cue" href="#scattered" aria-label="Scroll to the story"><span /></a>
      </section>

      <section id="scattered" className="story scattered">
        <Tag id="scattered" />
        <div className="story-copy" data-reveal><h2>Industrial knowledge is scattered</h2>
          <p>Procedures, drawings, readings, work history and shift notes live in different systems, formats and people. Answers depend on who remembers where to look.</p>
          <p className="stat"><Count value={F.evidenceSources} /> evidence sources the Workbench brings together</p></div>
        <div className="source-field">
          <SourceCard source={SOURCES[0]}><p className="doc-lines"><span /><span /><span /><span /></p><code>SOP-P204-001 §4.2</code></SourceCard>
          <SourceCard source={SOURCES[1]}><svg viewBox="0 0 120 60" aria-hidden="true"><circle cx="24" cy="30" r="12" /><path d="M36 30 H70 M70 20 v20 l16-10z M86 30 H112" /><text x="16" y="56">P-101A</text></svg></SourceCard>
          <SourceCard source={SOURCES[2]}><svg viewBox="0 0 120 50" aria-hidden="true"><polyline points="0,40 15,36 30,38 45,30 60,32 75,20 90,24 105,12 120,16" /></svg></SourceCard>
          <SourceCard source={SOURCES[3]}><p className="ticket"><strong>WO-7745</strong> Bearing inspection · closed</p></SourceCard>
          <SourceCard source={SOURCES[4]}><p className="note">“Pump sounded rough near end of shift.”</p></SourceCard>
        </div>
      </section>

      <section id="unify" className="story unify">
        <Tag id="unify" />
        <ConvergenceCanvas controllerRef={convergence} />
        <div className="unify-copy"><h2>One sovereign intelligence layer</h2></div>
        <div className="unify-notes"><p className="unify-note unify-note-a">Retrieved locally. Every answer cites its source.</p>
        <p className="unify-note unify-note-b">One layer over all five sources: on your hardware, under your governance.</p></div>
      </section>

      <section id="workflow" className="story workflow">
        <Tag id="workflow" />
        <div className="story-copy"><h2>Retrieve · Verify · Reason · Review · Approve</h2></div>
        <div className="flow-track" aria-hidden="true"><span className="flow-progress" /></div>
        <ol className="stations">{STATIONS.map(([name, text], index) => <li key={name} className="station" data-glass><span className="station-index">0{index + 1}</span><h3>{name}</h3><p>{text}</p></li>)}</ol>
      </section>

      <section id="reveal" className="story reveal">
        <Tag id="reveal" />
        <div className="story-copy" data-reveal><h2>One governed workbench</h2><p>Queries, evidence, approvals, knowledge and audit in one place. Restrained, keyboard-friendly and built for long shifts.</p></div>
        <figure className="reveal-stage">
          <div className="reveal-frame">
            <div className="reveal-chrome" aria-hidden="true"><i /><i /><i /><span>127.0.0.1 · Sovereign AI Workbench</span></div>
            <img src="/assets/landing/workbench-dashboard.webp" width="1424" height="900" loading="lazy" decoding="async"
              alt="The Workbench dashboard: system status, a P-204 vibration trend, the review queue, work orders and agent routes" />
          </div>
          <figcaption>The real Workbench dashboard, captured from a local instance. Records shown are synthetic, cited test data.</figcaption>
        </figure>
      </section>

      <section id="pid" className="story pid">
        <Tag id="pid" />
        <div className="story-copy" data-reveal><h2>P&ID evidence, never proof of plant state</h2>
          <p>Local OCR and optional local vision propose tag candidates. Registry matches need human-verified knowledge, and disagreements are flagged for review.</p>
          <p className="disclaimer">Drawings are as-drawn evidence only. They do not prove valve state, isolation, LOTO, permit status or process readiness.</p></div>
        <figure className="pid-figure" data-reveal data-glass>
          <svg viewBox="0 0 520 280" role="img" aria-label="Synthetic P&ID with OCR regions and a flagged visual candidate">
            <g className="pid-lines"><path className="draw" pathLength="1" d="M20 150 H150 M190 150 H300 M340 150 H402 M438 150 H500 M170 130 V60 H420 V132" /><circle cx="170" cy="150" r="20" /><path d="M300 136 v28 l40-14z M340 136 v28 l-40-14z" /><circle cx="420" cy="150" r="18" /><text x="410" y="155">FT</text></g>
            <g className="ocr-box"><rect x="140" y="180" width="70" height="26" /><text x="146" y="198">P-101A</text><text className="conf" x="146" y="222">OCR 0.96</text></g>
            <g className="ocr-box"><rect x="292" y="180" width="74" height="26" /><text x="298" y="198">XV-204D</text><text className="conf" x="298" y="222">OCR 0.91</text></g>
            <g className="vision-box"><rect x="392" y="100" width="60" height="96" /><text x="452" y="246" textAnchor="end">visual candidate · review</text></g>
          </svg>
          <figcaption>Synthetic illustration. Region colours are categories, never valve or equipment states.</figcaption>
        </figure>
      </section>

      <section id="maintenance" className="story maintenance">
        <Tag id="maintenance" />
        <div className="story-copy" data-reveal><h2>Maintenance and sensor intelligence</h2><p>Measured observations and tentative hypotheses stay visibly separate. Thresholds are supplied by people, and correlation is never presented as causation.</p></div>
        <figure className="chart-figure" data-reveal data-glass>
          <svg viewBox="0 0 520 220" role="img" aria-label="Synthetic vibration trend crossing a user-supplied threshold">
            <rect className="persist" x="345" y="20" width="110" height="170" rx="6" /><text className="persist-label" x="400" y="206" textAnchor="middle">3 readings above</text>
            <line className="threshold" x1="20" x2="500" y1="90" y2="90" /><text className="threshold-label" x="24" y="82">User-supplied threshold · 7.1 mm/s</text>
            <polyline className="draw trend" pathLength="1" points="20,170 70,160 120,164 170,150 220,146 270,130 320,110 360,84 400,76 440,70 480,66" />
          </svg>
          <figcaption>Synthetic illustration.</figcaption>
        </figure>
        <div className="evidence-cards">
          <article className="evidence observation" data-reveal data-glass><small>Observation · measured</small><p>Vibration above the 7.1 mm/s threshold for three consecutive readings.</p></article>
          <article className="evidence hypothesis" data-reveal data-glass><small>Hypothesis · tentative</small><p>Possible bearing wear. Unconfirmed; correlation is not causation.</p></article>
          <article className="evidence verify" data-reveal data-glass><small>Recommended verification</small><p>Review maintenance history and request a field inspection.</p></article>
        </div>
      </section>

      <section id="governance" className="story governance">
        <Tag id="governance" />
        <div className="story-copy" data-reveal><h2>Humans approve. The chain remembers.</h2>
          <p>Reviewers see the exact proposal, its evidence and its risk before deciding. The requester can never approve their own request, and every decision joins a hash-linked audit chain.</p>
          <p className="disclaimer">Tamper-evident, not tamper-proof: modification of the recorded chain is detectable. Approval releases advisory output only.</p></div>
        <div className="chain-figure"><ol className="chain" aria-label="Illustrative audit chain">
          {['GOVERNED_REVISION_CREATED', 'EVIDENCE_MANIFEST_CREATED', 'APPROVAL_DECISION_APPROVE', 'ADVISORY_RELEASE_SUCCESS'].map((event, index) => <li key={event} className="block" data-reveal data-glass>
            <small>#{1040 + index}</small><strong>{event}</strong><code>prev → hash</code></li>)}
        </ol>
        <p className="chain-caption">Illustration. The event names are real audit event types; the sequence numbers and hashes are placeholders.</p></div>
      </section>

      <section id="voice" className="story voice">
        <Tag id="voice" />
        <div className="story-copy" data-reveal><h2>Speak locally. Review every identifier.</h2>
          <p>Speech is transcribed on your hardware. Suspicious identifiers are highlighted and must be confirmed by you. Transcripts are never corrected silently.</p></div>
        <div className="voice-demo" data-reveal data-glass>
          <p className="raw">Raw transcript: “Check vibration trend on <mark>P204A</mark> since last shift”</p>
          <p className="reason">Flag: <strong>Malformed identifier</strong>. Resembles an equipment tag but does not match the expected format.</p>
          <p className="fixed">Your correction: “Check vibration trend on <code>P-204A</code> since last shift”</p>
          <p className="langs" lang="hi">P-204A का कंपन रुझान दिखाइए</p><p className="langs" lang="ta">P-204A அதிர்வு போக்கைக் காட்டு</p>
        </div>
      </section>

      <section id="sovereignty" className="story sovereignty">
        <Tag id="sovereignty" />
        <div className="story-copy" data-reveal><h2>Your hardware. Your boundary.</h2>
          <p>Inference, retrieval, storage and speech run on local services. No hosted AI is configured for confidential work.</p>
          <p className="disclaimer">Offline-capable, not automatically air-gapped: network isolation is enforced by your site controls.</p></div>
        <div className="topology" data-reveal data-glass role="img" aria-label="Local services inside the site boundary">
          <span className="node core">Workbench API</span>
          {['Ollama · qwen3.5 9B / 4B', 'PostgreSQL', 'Qdrant', 'Local STT / TTS', 'Local files'].map(node => <span key={node} className="node">{node}</span>)}
          <span className="boundary-label">Site boundary</span>
        </div>
      </section>

      <section id="ecosystem" className="story ecosystem">
        <Tag id="ecosystem" />
        <div className="story-copy" data-reveal><h2>Government ecosystem, accurately represented</h2><p>Confidential plant data may only use locally approved resources. Public services stay optional and are never sent confidential data.</p></div>
        <ul className="eco-grid">{ECOSYSTEM.map(([name, status, note]) => <li key={name} data-reveal data-glass><strong>{name}</strong><span className="badge">{status}</span><p>{note}</p></li>)}</ul>
      </section>

      <section id="enter" className="story enter">
        <Tag id="enter" />
        <img className="enter-mark brand-img" src="/assets/branding/sovereign-mark.png" alt="" width="220" height="220" />
        <h2 data-reveal>Enter Sovereign Workbench</h2>
        <p data-reveal>Local inference. Cited evidence. Human approval. Tamper-evident audit.</p>
        <Link className="button primary large" to={enter}>Enter Sovereign Workbench</Link>
      </section>
    </main>
    <footer className="landing-footer"><Logo variant="horizontal" decorative className="landing-logo" /><p>Facts as of {F.asOf}: {F.benchmarkCases}-case benchmark, {F.frozenBenchmarkFiles} hash-verified frozen benchmark files. Advisory recommendations only.</p></footer>
  </div>
}
