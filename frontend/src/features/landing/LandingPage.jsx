import { useEffect, useRef } from 'react'
import { Link } from 'react-router'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import { useSession } from '../../app/session.jsx'
import { Logo } from '../../components/ui.jsx'
import { PRODUCT_FACTS as F, SOURCES, STORY, canvasSize, createParticles, particlePosition, smoothstep } from './landingModel.js'
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

const Tag = ({ id }) => {
  const [code, number] = STORY.find(item => item.id === id).tag.split('-')
  return <span className="tag-bubble" aria-hidden="true"><span>{code}</span><span>{number}</span></span>
}

const Count = ({ value }) => <span className="count" data-count={value}>{value.toLocaleString()}</span>

function SourceCard({ source, children }) {
  return <article className="source-card" style={{ '--accent': source.color }}><header><span className="dot" />{source.label}</header>{children}<footer>{source.detail}</footer></article>
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
  const session = useSession()
  const enter = session.status === 'authenticated' ? '/app/dashboard' : '/login'

  useEffect(() => { document.title = 'Sovereign AI Workbench · Governed industrial intelligence on your own infrastructure' }, [])

  useGSAP(() => {
    gsap.registerPlugin(ScrollTrigger)
    const mm = gsap.matchMedia()
    mm.add({ motion: '(prefers-reduced-motion: no-preference)', desktop: '(min-width: 1024px)' }, ({ conditions }) => {
      const { motion, desktop } = conditions
      if (!motion) { convergence.current?.setProgress(1); return undefined }
      root.current.classList.add('motion')
      gsap.fromTo('.spine-path', { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: 'none',
        scrollTrigger: { trigger: root.current, start: 'top top', end: 'bottom bottom', scrub: 0.5 } })
      gsap.from('.hero-word', { yPercent: 110, opacity: 0, stagger: 0.08, duration: 1, ease: 'power3.out' })
      gsap.from('.hero-mark', { scale: 0.7, opacity: 0, duration: 1.4, ease: 'power2.out' })
      gsap.to('.hero-mark', { yPercent: 22, ease: 'none', scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true } })
      gsap.utils.toArray('[data-reveal]').forEach(element => gsap.from(element, { y: 36, opacity: 0, duration: 0.9, ease: 'power2.out',
        scrollTrigger: { trigger: element, start: 'top 85%', once: true } }))
      gsap.utils.toArray('[data-count]').forEach(element => {
        const counter = { value: 0 }
        gsap.to(counter, { value: Number(element.dataset.count), duration: 1.6, ease: 'power1.out',
          scrollTrigger: { trigger: element, start: 'top 90%', once: true },
          onUpdate: () => { element.textContent = Math.round(counter.value).toLocaleString() } })
      })
      const offsets = [[-70, -45, -7], [60, -25, 6], [-35, 40, -4], [80, 45, 7], [-55, 15, -3]]
      gsap.to('.source-card', { x: i => offsets[i][0] * (desktop ? 2 : 1), y: i => offsets[i][1] * (desktop ? 2 : 1), rotate: i => offsets[i][2], ease: 'none',
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
    <svg className="spine" viewBox="0 0 24 1000" preserveAspectRatio="none" aria-hidden="true">
      <path className="spine-track" d="M12 0 V1000" pathLength="1" />
      <path className="spine-path" d="M12 0 V180 H6 V420 H18 V640 H12 V1000" pathLength="1" />
    </svg>
    <main id="main">
      <section id="hero" className="hero">
        <Tag id="hero" />
        <img className="hero-mark brand-img" src="/assets/branding/sovereign-mark.png" alt="" width="458" height="458" fetchPriority="high" />
        <p className="eyebrow">Governed industrial intelligence · on your own infrastructure</p>
        <h1 aria-label="Sovereign AI Workbench">{['Sovereign', 'AI', 'Workbench'].map(word => <span key={word} className="hero-word-mask" aria-hidden="true"><span className="hero-word">{word}</span></span>)}</h1>
        <p className="lede">Ask questions of your procedures, drawings, sensors and maintenance history. Every answer cites its evidence, every operational recommendation waits for a human, and nothing leaves your site.</p>
        <div className="hero-actions"><Link className="button primary" to={enter}>Enter Sovereign Workbench</Link><a className="button ghost" href="#scattered">See how it works</a></div>
        <ul className="fact-strip" aria-label="Verified product facts">
          <li><Count value={F.hostedAiCalls} /><span>hosted AI calls in the confidential path</span></li>
          <li><Count value={F.localModels} /><span>local models, risk-routed</span></li>
          <li><Count value={F.languages} /><span>languages: English, हिन्दी, தமிழ்</span></li>
          <li><Count value={F.backendTests} /><span>automated backend tests ({F.asOf})</span></li>
        </ul>
      </section>

      <section id="scattered" className="story scattered">
        <Tag id="scattered" />
        <div className="story-copy" data-reveal><p className="eyebrow">The problem</p><h2>Industrial knowledge is scattered</h2>
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
        <div className="unify-copy"><p className="eyebrow">The answer</p><h2>One sovereign intelligence layer</h2></div>
        <p className="unify-note unify-note-a">Retrieved locally. Every answer cites its source.</p>
        <p className="unify-note unify-note-b">One layer over all five sources: on your hardware, under your governance.</p>
      </section>

      <section id="workflow" className="story workflow">
        <Tag id="workflow" />
        <div className="story-copy"><p className="eyebrow">The governed workflow</p><h2>Retrieve · Verify · Reason · Review · Approve</h2></div>
        <div className="flow-track" aria-hidden="true"><span className="flow-progress" /></div>
        <ol className="stations">{STATIONS.map(([name, text], index) => <li key={name} className="station"><span className="station-index">0{index + 1}</span><h3>{name}</h3><p>{text}</p></li>)}</ol>
      </section>

      <section id="reveal" className="story reveal">
        <Tag id="reveal" />
        <div className="story-copy" data-reveal><p className="eyebrow">The workbench</p><h2>One governed workbench</h2><p>Queries, evidence, approvals, knowledge and audit in one place. Restrained, keyboard-friendly and built for long shifts.</p></div>
        <div className="reveal-stage"><div className="reveal-frame" role="img" aria-label="Illustrative Workbench interface with synthetic values">
          <div className="mock-nav"><span /><span /><span /><span /><span /></div>
          <div className="mock-body">
            <div className="mock-card"><small>Pending reviews</small><strong>—</strong></div>
            <div className="mock-card"><small>Evidence sufficiency</small><div className="mock-bars"><i style={{ '--h': '70%' }} /><i style={{ '--h': '45%' }} /><i style={{ '--h': '20%' }} /></div></div>
            <div className="mock-card wide"><small>Routing</small><p><code>{F.primaryModel}</code> deep reasoning · <code>{F.fastModel}</code> bounded tasks</p></div>
            <div className="mock-card wide draft"><small>Draft · human approval required</small><p>Advisory recommendation with cited evidence.</p></div>
          </div>
          <p className="mock-label">Illustrative interface · synthetic values</p>
        </div></div>
      </section>

      <section id="pid" className="story pid">
        <Tag id="pid" />
        <div className="story-copy" data-reveal><p className="eyebrow">Multimodal P&ID</p><h2>P&ID evidence, never proof of plant state</h2>
          <p>Local OCR and optional local vision propose tag candidates. Registry matches need human-verified knowledge, and disagreements are flagged for review.</p>
          <p className="disclaimer">Drawings are as-drawn evidence only. They do not prove valve state, isolation, LOTO, permit status or process readiness.</p></div>
        <figure className="pid-figure" data-reveal>
          <svg viewBox="0 0 520 280" role="img" aria-label="Synthetic P&ID with OCR regions and a flagged visual candidate">
            <g className="pid-lines"><path className="draw" pathLength="1" d="M20 150 H150 M190 150 H300 M340 150 H500 M170 110 V60 H420 V130" /><circle cx="170" cy="150" r="20" /><path d="M300 136 v28 l40-14z M340 136 v28 l-40-14z" /><circle cx="420" cy="150" r="18" /><text x="410" y="155">FT</text></g>
            <g className="ocr-box"><rect x="140" y="180" width="70" height="26" /><text x="146" y="198">P-101A</text><text className="conf" x="146" y="222">OCR 0.96</text></g>
            <g className="ocr-box"><rect x="292" y="180" width="74" height="26" /><text x="298" y="198">XV-204D</text><text className="conf" x="298" y="222">OCR 0.91</text></g>
            <g className="vision-box"><rect x="392" y="100" width="60" height="96" /><text x="360" y="92">visual candidate · review</text></g>
          </svg>
          <figcaption>Synthetic illustration. Region colours are categories, never valve or equipment states.</figcaption>
        </figure>
      </section>

      <section id="maintenance" className="story maintenance">
        <Tag id="maintenance" />
        <div className="story-copy" data-reveal><p className="eyebrow">Maintenance and sensors</p><h2>Maintenance and sensor intelligence</h2><p>Measured observations and tentative hypotheses stay visibly separate. Thresholds are supplied by people, and correlation is never presented as causation.</p></div>
        <figure className="chart-figure" data-reveal>
          <svg viewBox="0 0 520 220" role="img" aria-label="Synthetic vibration trend crossing a user-supplied threshold">
            <rect className="persist" x="330" y="20" width="150" height="170" />
            <line className="threshold" x1="20" x2="500" y1="90" y2="90" /><text className="threshold-label" x="24" y="82">User-supplied threshold · 7.1 mm/s</text>
            <polyline className="draw trend" pathLength="1" points="20,170 70,160 120,164 170,150 220,146 270,130 320,110 360,84 400,76 440,70 480,66" />
          </svg>
          <figcaption>Synthetic illustration.</figcaption>
        </figure>
        <div className="evidence-cards">
          <article className="evidence observation" data-reveal><small>Observation · measured</small><p>Vibration above the 7.1 mm/s threshold for three consecutive readings.</p></article>
          <article className="evidence hypothesis" data-reveal><small>Hypothesis · tentative</small><p>Possible bearing wear. Unconfirmed; correlation is not causation.</p></article>
          <article className="evidence verify" data-reveal><small>Recommended verification</small><p>Review maintenance history and request a field inspection.</p></article>
        </div>
      </section>

      <section id="governance" className="story governance">
        <Tag id="governance" />
        <div className="story-copy" data-reveal><p className="eyebrow">Human governance</p><h2>Humans approve. The chain remembers.</h2>
          <p>Reviewers see the exact proposal, its evidence and its risk before deciding. The requester can never approve their own request, and every decision joins a hash-linked audit chain.</p>
          <p className="disclaimer">Tamper-evident, not tamper-proof: modification of the recorded chain is detectable. Approval releases advisory output only.</p></div>
        <ol className="chain" aria-label="Illustrative audit chain">
          {['GOVERNED_REVISION_CREATED', 'EVIDENCE_MANIFEST_CREATED', 'APPROVAL_DECISION_APPROVE', 'ADVISORY_RELEASE_SUCCESS'].map((event, index) => <li key={event} className="block" data-reveal>
            <small>#{1040 + index}</small><strong>{event}</strong><code>prev → hash</code></li>)}
        </ol>
      </section>

      <section id="voice" className="story voice">
        <Tag id="voice" />
        <div className="story-copy" data-reveal><p className="eyebrow">Multilingual local voice</p><h2>Speak locally. Review every identifier.</h2>
          <p>Speech is transcribed on your hardware. Suspicious identifiers are highlighted and must be confirmed by you. Transcripts are never corrected silently.</p></div>
        <div className="voice-demo" data-reveal>
          <p className="raw">Raw transcript: “Check vibration trend on <mark>P204A</mark> since last shift”</p>
          <p className="reason">Flag: <strong>Malformed identifier</strong>. Resembles an equipment tag but does not match the expected format.</p>
          <p className="fixed">Your correction: “Check vibration trend on <code>P-204A</code> since last shift”</p>
          <p className="langs" lang="hi">P-204A का कंपन रुझान दिखाइए</p><p className="langs" lang="ta">P-204A அதிர்வு போக்கைக் காட்டு</p>
        </div>
      </section>

      <section id="sovereignty" className="story sovereignty">
        <Tag id="sovereignty" />
        <div className="story-copy" data-reveal><p className="eyebrow">Sovereignty</p><h2>Your hardware. Your boundary.</h2>
          <p>Inference, retrieval, storage and speech run on local services. No hosted AI is configured for confidential work.</p>
          <p className="disclaimer">Offline-capable, not automatically air-gapped: network isolation is enforced by your site controls.</p></div>
        <div className="topology" data-reveal role="img" aria-label="Local services inside the site boundary">
          <span className="node core">Workbench API</span>
          {['Ollama · qwen3.5 9B / 4B', 'PostgreSQL', 'Qdrant', 'Local STT / TTS', 'Local files'].map(node => <span key={node} className="node">{node}</span>)}
          <span className="boundary-label">Site boundary</span>
        </div>
      </section>

      <section id="ecosystem" className="story ecosystem">
        <Tag id="ecosystem" />
        <div className="story-copy" data-reveal><p className="eyebrow">Government ecosystem</p><h2>Government ecosystem, accurately represented</h2><p>Confidential plant data may only use locally approved resources. Public services stay optional and are never sent confidential data.</p></div>
        <ul className="eco-grid">{ECOSYSTEM.map(([name, status, note]) => <li key={name} data-reveal><strong>{name}</strong><span className="badge">{status}</span><p>{note}</p></li>)}</ul>
      </section>

      <section id="enter" className="story enter">
        <Tag id="enter" />
        <img className="enter-mark brand-img" src="/assets/branding/sovereign-mark.png" alt="" width="220" height="220" loading="lazy" />
        <h2 data-reveal>Enter Sovereign Workbench</h2>
        <p data-reveal>Local inference. Cited evidence. Human approval. Tamper-evident audit.</p>
        <Link className="button primary large" to={enter}>Enter Sovereign Workbench</Link>
      </section>
    </main>
    <footer className="landing-footer"><Logo variant="horizontal" decorative className="landing-logo" /><p>Facts as of {F.asOf}: {F.benchmarkCases}-case benchmark, {F.frozenBenchmarkFiles} hash-verified frozen benchmark files. Advisory recommendations only.</p></footer>
  </div>
}
