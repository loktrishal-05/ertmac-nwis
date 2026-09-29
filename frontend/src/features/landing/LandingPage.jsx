import { useEffect, useRef } from 'react'
import { Link } from 'react-router'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import { useGSAP } from '@gsap/react'
import { useSession } from '../../app/session.jsx'
import { Logo } from '../../components/ui.jsx'
import { FACTS, PRODUCT, SCENARIO, STORY } from './landingModel.js'
import { createAtmosphere } from './atmosphere.js'
import SubsurfaceCanvas from './SubsurfaceCanvas.jsx'
import './landing.css'

// One fixed backdrop for the whole page. Reduced motion draws a single still frame; Save-Data or no WebGL keep the CSS gradient.
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

const stillOnly = () => typeof window === 'undefined' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || !!navigator.connection?.saveData
// Glass panels lean toward the cursor and catch light on the edge nearest to it.
function useMagneticGlass(root) {
  useEffect(() => {
    if (stillOnly() || !window.matchMedia?.('(hover: hover) and (pointer: fine)').matches) return undefined
    const cards = [...root.current.querySelectorAll('[data-glass]')]
    const move = event => {
      const card = event.currentTarget, rect = card.getBoundingClientRect()
      const x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height
      const tilt = Math.min(6, 2400 / Math.max(rect.width, rect.height))
      card.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`)
      card.style.setProperty('--my', `${(y * 100).toFixed(1)}%`)
      card.style.rotate = `${(0.5 - y).toFixed(3)} ${(x - 0.5).toFixed(3)} 0 ${(Math.hypot(x - 0.5, y - 0.5) * tilt * 2).toFixed(2)}deg`
    }
    const leave = event => { event.currentTarget.style.rotate = '' }
    cards.forEach(card => { card.addEventListener('pointermove', move); card.addEventListener('pointerleave', leave) })
    return () => cards.forEach(card => { card.removeEventListener('pointermove', move); card.removeEventListener('pointerleave', leave); leave({ currentTarget: card }) })
  }, [root])
}

const Tag = ({ id }) => {
  const [code, number] = STORY.find(item => item.id === id).tag.split('-')
  return <span className="tag-bubble" aria-hidden="true"><span>{code}</span><span>{number}</span></span>
}

// Deterministic illustrative torque trace (synthetic replay): steady, then a persistent rise in the last third.
const TORQUE = Array.from({ length: 64 }, (_, i) => {
  const late = Math.max(0, i - 42) / 22
  return [8 + i * 7.6, 150 - (Math.sin(i * 0.55) * 7 + Math.sin(i * 1.7) * 3 + late * 62)]
})
const pct = v => `${Math.round(v * 100)}%`

// Formation correlation figure: offsets start offset by measured depth, scroll aligns them by TVD.
const BANDS = [['NAMSANG', 30, 92], ['GIRUJAN', 92, 170], ['TIPAM_A', 170, 238], ['TIPAM_B', 238, 300], ['BARAIL', 300, 350]]
const TRACKS = [{ id: 'ACTIVE-01', x: 40, active: true }, { id: 'OFF-04', x: 210, shift: 44, events: [[204, 'stuck'], [226, 'loss']] }, { id: 'OFF-09', x: 380, shift: -36, events: [[212, 'stuck'], [182, 'torque']] }]
function CorrelationFigure() {
  return <svg className="corr-figure" viewBox="0 0 520 370" role="img" aria-label="Illustration: the active well and two offsets aligned by true vertical depth, with historical stuck-pipe and mud-loss events at the equivalent Tipam interval, just ahead of the active well's look-ahead window.">
    {TRACKS.slice(0, -1).map((t, i) => BANDS.map(([name, top]) => <line key={`${i}-${name}`} className="corr-link" x1={t.x + 100} x2={TRACKS[i + 1].x} y1={top} y2={top} />))}
    {TRACKS.map(t => <g key={t.id} className={`corr-track${t.active ? ' is-active' : ''}`} data-shift={t.shift || 0}>
      <text className="corr-name" x={t.x + 50} y={18} textAnchor="middle">{t.id}</text>
      {BANDS.map(([name, top, base], i) => <g key={name}><rect x={t.x} y={top} width="100" height={base - top} className={`band band-${i}`} /><line className="corr-top" x1={t.x} x2={t.x + 100} y1={top} y2={top} />{t.active && <text className="band-name" x={t.x + 6} y={top + 14}>{name}</text>}</g>)}
      {t.active && <><rect className="corr-window" x={t.x - 6} y="196" width="112" height="40" /><line className="bit" x1={t.x - 8} x2={t.x + 108} y1="196" y2="196" /><text className="bit-label" x={t.x + 4} y="230">bit · look-ahead 100 m</text></>}
      {(t.events || []).map(([y, kind]) => <circle key={`${y}${kind}`} className={`corr-event ev-${kind}`} cx={t.x + 78} cy={y} r="7" />)}
    </g>)}
  </svg>
}

function PlanView() {
  return <svg className="plan-figure" viewBox="-170 -150 340 300" role="img" aria-label="Illustration: nearby wells within 2 and 5 km of ACTIVE-01. The closest well ranks sixth because it lies across a fault; OFF-04 and OFF-09 rank first and second.">
    <circle className="ring" r="56" /><circle className="ring" r="132" />
    <text className="ring-label" x="4" y="-60">2 km</text><text className="ring-label" x="4" y="-136">5 km</text>
    <path className="fault" d="M-160 40 C -60 20, 10 50, 150 -10" /><text className="fault-label" x="-150" y="30">mapped fault</text>
    {SCENARIO.offsets.map(o => <g key={o.id} className={`plan-well${o.top ? ' is-top' : ''}${o.note ? ' is-weak' : ''}`} transform={`translate(${o.x} ${o.y})`}>
      <circle r={o.top ? 7 : 5.5} /><text x="10" y="4">{o.id} · #{o.rank}</text>{o.note && <text className="plan-note" x="10" y="18">{o.note}</text>}</g>)}
    <g className="plan-active"><circle r="9" /><text x="-12" y="-16" textAnchor="middle">ACTIVE-01</text></g>
  </svg>
}

export default function LandingPage() {
  const root = useRef(null)
  const hero = useRef(null)
  const session = useSession()
  const signedIn = session.status === 'authenticated'
  const enter = signedIn ? '/app/dashboard' : '/login'

  useMagneticGlass(root)
  useEffect(() => { document.title = `${PRODUCT.name} · ${PRODUCT.subtitle}` }, [])

  useGSAP(() => {
    gsap.registerPlugin(ScrollTrigger, SplitText)
    const mm = gsap.matchMedia()
    mm.add({ motion: '(prefers-reduced-motion: no-preference)', desktop: '(min-width: 1024px)' }, ({ conditions }) => {
      const { motion, desktop } = conditions
      if (!motion) return undefined
      root.current.classList.add('motion')
      // The depth rail streams downward with the scroll and flares with scroll speed.
      const spine = root.current.querySelector('.spine')
      if (spine) ScrollTrigger.create({ trigger: root.current, start: 'top top', end: 'bottom bottom', onUpdate: self => {
        spine.style.setProperty('--off', (-window.scrollY / window.innerHeight * 0.35).toFixed(4))
        gsap.to(spine, { '--energy': Math.min(1, Math.abs(self.getVelocity()) / 2500), duration: 0.2, overwrite: true })
        gsap.to(spine, { '--energy': 0, duration: 1.4, delay: 0.25, ease: 'power2.out' })
      } })
      gsap.utils.toArray('.story h2').forEach(heading => {
        const split = SplitText.create(heading, { type: 'words', wordsClass: 'word' })
        gsap.from(split.words, { opacity: 0, filter: 'blur(14px)', yPercent: 35, duration: 1.1, stagger: 0.06, ease: 'expo.out', clearProps: 'filter', scrollTrigger: { trigger: heading, start: 'top 88%', once: true } })
      })
      gsap.from('.hero-title .line', { yPercent: 105, duration: 1.3, stagger: 0.12, delay: 0.3, ease: 'expo.out' })
      gsap.from('.hero-copy > :not(h1)', { y: 24, opacity: 0, filter: 'blur(8px)', duration: 1.1, stagger: 0.1, delay: 0.7, ease: 'expo.out', clearProps: 'filter' })
      ScrollTrigger.create({ trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true, onUpdate: self => hero.current?.setScroll(self.progress) })
      gsap.to('.hero-copy', { yPercent: -12, opacity: 0.2, ease: 'none', scrollTrigger: { trigger: '#hero', start: '35% top', end: 'bottom top', scrub: true } })
      gsap.utils.toArray('[data-reveal]').forEach(element => gsap.from(element, { y: 36, opacity: 0, filter: 'blur(10px)', duration: 1, ease: 'expo.out', clearProps: 'filter', scrollTrigger: { trigger: element, start: 'top 86%', once: true } }))
      // Reports → structured events: the source sentence is highlighted, then the record fills in field by field.
      gsap.fromTo('.ddr mark', { backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%', ease: 'none', scrollTrigger: { trigger: '#reports', start: 'top 70%', end: 'top 25%', scrub: true } })
      gsap.from('.record-row', { opacity: 0, x: 24, stagger: 0.12, ease: 'none', scrollTrigger: { trigger: '#reports', start: 'top 55%', end: 'center 40%', scrub: true } })
      // Nearby wells appear around the active well; relevance then separates the analogs from the merely close.
      const plan = root.current.querySelector('.plan-figure')
      ScrollTrigger.create({ trigger: '#nearby', start: 'top 75%', once: true, onEnter: () => plan?.classList.add('is-shown') })
      ScrollTrigger.create({ trigger: '#nearby', start: 'top 35%', onEnter: () => plan?.classList.add('is-ranked'), onLeaveBack: () => plan?.classList.remove('is-ranked') })
      gsap.from('.rank-list li', { opacity: 0, y: 12, stagger: 0.08, scrollTrigger: { trigger: '.rank-list', start: 'top 80%', once: true } })
      // Correlation: measured-depth misalignment resolves by TVD, then incidents appear at the equivalent interval.
      const corr = gsap.timeline({ scrollTrigger: { trigger: '#correlation', start: desktop ? 'top top' : 'top 70%', end: desktop ? '+=180%' : 'bottom 60%', pin: desktop, scrub: 0.6 } })
      root.current.querySelectorAll('.corr-track').forEach(track => { const shift = Number(track.dataset.shift); if (shift) corr.fromTo(track, { y: shift }, { y: 0, duration: 0.4, ease: 'power2.inOut' }, 0.05) })
      corr.fromTo('.corr-link', { opacity: 0 }, { opacity: 1, duration: 0.15 }, 0.42)
        .fromTo('.corr-event', { scale: 0, transformOrigin: 'center', transformBox: 'fill-box' }, { scale: 1, stagger: 0.05, duration: 0.15, ease: 'back.out(3)' }, 0.58)
        .fromTo(".corr-window", { opacity: 0 }, { opacity: 1, duration: 0.12 }, 0.7)
        .fromTo('.corr-note-a', { opacity: 1 }, { opacity: 0, duration: 0.08 }, 0.36)
        .fromTo('.corr-note-b', { opacity: 0 }, { opacity: 1, duration: 0.08 }, 0.4)
        .to('.corr-note-b', { opacity: 0, duration: 0.08 }, 0.56)
        .fromTo('.corr-note-c', { opacity: 0 }, { opacity: 1, duration: 0.08 }, 0.6)
      gsap.utils.toArray('.draw').forEach(path => gsap.fromTo(path, { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: 'none', scrollTrigger: { trigger: path.closest('section'), start: 'top 70%', end: 'center 45%', scrub: true } }))
      gsap.from('.risk-card', { y: 40, opacity: 0, stagger: 0.12, duration: 0.9, ease: 'expo.out', scrollTrigger: { trigger: '#lookahead', start: 'top 65%', once: true } })
      gsap.from('.risk-fill', { width: 0, stagger: 0.12, duration: 1.2, ease: 'expo.out', scrollTrigger: { trigger: '#lookahead', start: 'top 60%', once: true } })
      const element = root.current
      return () => element?.classList.remove('motion')
    })
  }, { scope: root })

  return <div className="landing" data-theme="dark" ref={root}>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="landing-header">
      <Link to="/" aria-label={`${PRODUCT.name} home`} className="landing-brand"><Logo variant="horizontal" decorative /></Link>
      <nav aria-label="Story"><a href="#nearby">Offset wells</a><a href="#correlation">Correlation</a><a href="#lookahead">Look-ahead</a><a href="#evidence">Evidence</a></nav>
      <Link className="button primary" to={enter}>{signedIn ? 'Open NWIS' : 'Sign in'}</Link>
    </header>
    <Atmosphere />
    <svg className="spine" viewBox="0 0 24 1000" preserveAspectRatio="none" aria-hidden="true">
      <path className="spine-track" d="M12 0 V1000" /><path className="spine-glow" d="M12 0 V1000" pathLength="1" /><path className="spine-light" d="M12 0 V1000" pathLength="1" />
    </svg>
    <main id="main">
      <section id="hero" className="hero">
        <Tag id="hero" />
        <SubsurfaceCanvas className="hero-canvas" apiRef={hero} />
        <div className="hero-scrim" aria-hidden="true" />
        <div className="hero-copy">
          <p className="hero-kicker">{PRODUCT.context.join(' · ')}</p>
          <h1 className="hero-title"><span className="line-mask"><span className="line">eRTMAC sees the live well.</span></span> <span className="line-mask"><span className="line"><em>NWIS remembers nearby wells.</em></span></span></h1>
          <p className="lede">Know what nearby wells learned before the bit reaches the same interval. {PRODUCT.name}, the {PRODUCT.subtitle}: AI-powered offset-well knowledge and decision support for drilling operations.</p>
          <div className="hero-actions"><Link className="button primary" to={enter}>{signedIn ? 'Open NWIS' : 'Enter NWIS'}</Link><a className="button ghost" href="#reports">See how it works</a></div>
          <p className="hero-facts" aria-label="Prototype design facts">{FACTS.map(([value, label]) => <span key={label}><span className="fact-num">{value}</span> {label}</span>)}</p>
        </div>
        <a className="scroll-cue" href="#reports" aria-label="Scroll to the story"><span /></a>
      </section>

      <section id="reports" className="story reports">
        <Tag id="reports" />
        <div className="story-copy" data-reveal><h2>Historical reports become structured drilling events</h2>
          <p>Well completion and daily drilling reports are parsed with layout-aware OCR. Every event keeps its original wording, depth, formation, mitigation, outcome and the page it came from.</p></div>
        <div className="report-flow">
          <article className="ddr" data-glass aria-label="Excerpt of a synthetic daily drilling report">
            <header><strong>Daily Drilling Report</strong><span>OFF-04 · page 2 · synthetic</span></header>
            <p className="ddr-line" /><p className="ddr-line short" />
            <p className="ddr-text">06:40 <mark>String stuck at 2,529 m MD after connection; unable to rotate, circulation established. Suspected differential sticking across Tipam sand.</mark> Spotted pipe-release pill.</p>
            <p className="ddr-line" /><p className="ddr-line shorter" />
          </article>
          <span className="flow-arrow" aria-hidden="true">→</span>
          <dl className="record" data-glass aria-label="Structured event extracted from the report">
            {SCENARIO.record.map(([k, v]) => <div key={k} className="record-row"><dt>{k}</dt><dd>{v}</dd></div>)}
          </dl>
        </div>
      </section>

      <section id="nearby" className="story nearby">
        <Tag id="nearby" />
        <div className="story-copy" data-reveal><h2>Nearby is not the same as analogous</h2>
          <p>A radius query finds candidate offsets around the active well. A transparent similarity score then ranks them by formation, depth overlap, trajectory, program context and data quality, so a formation-matched well can outrank a closer one across a fault.</p>
          <ol className="rank-list">
            <li><strong>#1 OFF-04</strong><span>3.1 km · formation 0.95 · depth 0.92</span></li>
            <li><strong>#2 OFF-09</strong><span>4.4 km · formation 0.92 · depth 0.90</span></li>
            <li className="is-weak"><strong>#6 OFF-02</strong><span>1.1 km · formation 0.22 · depth 0.30 · closest well</span></li>
          </ol></div>
        <figure className="plan" data-glass><PlanView /><figcaption>Illustrative synthetic scenario. Distances come from the backend spatial query; ranking is deterministic, never an LLM.</figcaption></figure>
      </section>

      <section id="correlation" className="story correlation">
        <Tag id="correlation" />
        <div className="corr-copy"><h2>Formation-aligned, not guessed</h2>
          <div className="corr-notes">
            <p className="corr-note corr-note-a">Measured depth misleads: deviated wells reach the same rock at different MD.</p>
            <p className="corr-note corr-note-b">NWIS aligns wells by TVD and formation tops, and shows where tops are interpreted.</p>
            <p className="corr-note corr-note-c">Historical stuck pipe and losses appear at the equivalent Tipam interval, just ahead of the bit.</p>
          </div></div>
        <figure className="corr-stage" data-glass><CorrelationFigure /><figcaption>Illustration only. Dashed connectors are interpreted correlations; distance never implies geological continuity.</figcaption></figure>
      </section>

      <section id="telemetry" className="story telemetry">
        <Tag id="telemetry" />
        <div className="story-copy" data-reveal><h2>Current telemetry joins the history</h2>
          <p>Drilling parameters stream in through a replay adapter today and a WITSML / ETP-ready interface later. Persistent trends, not single spikes, adjust the look-ahead, and stale data is shown as stale.</p></div>
        <figure className="trace" data-glass>
          <svg viewBox="0 0 500 170" role="img" aria-label="Illustrative synthetic torque trace that rises persistently over the last third of the window">
            <line className="trace-grid" x1="0" x2="500" y1="40" y2="40" /><line className="trace-grid" x1="0" x2="500" y1="100" y2="100" />
            <rect className="persist" x="326" y="12" width="164" height="150" rx="6" />
            <polyline className="draw trace-line" pathLength="1" points={TORQUE.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} />
            <text className="trace-label" x="8" y="18">TORQUE · SIMULATED REPLAY</text><text className="persist-label" x="408" y="158" textAnchor="middle">persistent rise · +21%</text>
          </svg>
          <figcaption>Synthetic replay data. NWIS never presents replay as an Oil India or eRTMAC live feed.</figcaption>
        </figure>
      </section>

      <section id="lookahead" className="story lookahead">
        <Tag id="lookahead" />
        <div className="story-copy" data-reveal><h2>Risk look-ahead: the next 50, 100, 150 m</h2>
          <p>Each hazard gets its own probability, confidence, trend and evidence count, with the historical and live-telemetry contributions kept separate. There is no single overall AI risk.</p></div>
        <div className="risk-row">{SCENARIO.risks.map(([name, p, c, trend]) => <article key={name} className="risk-card" data-glass data-high={p >= 0.6 || undefined}>
          <header><h3>{name}</h3><span className="risk-trend">{trend === 'rising' ? '↑ rising' : '→ steady'}</span></header>
          <p className="risk-p">{pct(p)}<small> next 100 m</small></p>
          <p className="risk-c">Confidence {pct(c)}</p><span className="risk-bar" aria-hidden="true"><span className="risk-fill" style={{ width: pct(p) }} /></span>
        </article>)}</div>
        <p className="scenario-note">Illustrative synthetic scenario. Probabilities come from the hybrid risk engine; the language model only explains the evidence.</p>
      </section>

      <section id="evidence" className="story evidence">
        <Tag id="evidence" />
        <div className="story-copy" data-reveal><h2>Why this alert? The evidence, not a black box</h2>
          <p>Every alert opens to the supporting offset wells and their similarity, the historical event depths, the cited report passages, the telemetry features, what evidence is missing and why confidence is what it is.</p></div>
        <aside className="drawer-mock" data-glass data-reveal aria-label="Illustration of the evidence drawer">
          <p className="drawer-eyebrow">Why this alert?</p><h3>Stuck pipe · 72% over the next 100 m</h3>
          <dl><div><dt>Supporting wells</dt><dd>OFF-04 (#1, 0.89) · OFF-09 (#2, 0.85)</dd></div><div><dt>Event depths</dt><dd>2,455 m and 2,470 m TVD · Tipam A</dd></div><div><dt>Live feature</dt><dd>Torque +21% over 25 samples</dd></div><div><dt>Missing</dt><dd>One offset depth has low OCR confidence</dd></div></dl>
          <blockquote>“String stuck at 2,529 m MD after connection; unable to rotate…” <cite>DDR-OFF04 · p.2</cite></blockquote>
          <p className="drawer-foot">Advisory only. The drilling engineer reviews, acknowledges or records insufficient evidence; every decision is audited.</p>
        </aside>
      </section>

      <section id="architecture" className="story architecture">
        <Tag id="architecture" />
        <div className="story-copy" data-reveal><h2>Built beside eRTMAC, not in place of it</h2>
          <p>eRTMAC remains the live eye. NWIS is the institutional memory layer: spatial search, formation correlation, hybrid risk and cited evidence, running on local infrastructure.</p>
          <p className="disclaimer">{PRODUCT.positioning}; not deployed at Oil India. The prototype uses a clearly labelled synthetic demo dataset and never commands rig equipment.</p></div>
        <div className="topology" data-glass data-reveal role="img" aria-label="NWIS architecture: data sources feed spatial, knowledge and risk services inside the site boundary">
          <span className="node core">NWIS API · offset similarity · hybrid risk</span>
          {['WCR / DDR ingestion · OCR', 'PostgreSQL + PostGIS', 'Qdrant evidence search', 'Local LLM · explanation only', 'WITSML / ETP-ready adapter', 'Tamper-evident audit'].map(node => <span key={node} className="node">{node}</span>)}
          <span className="boundary-label">Site boundary</span>
        </div>
      </section>

      <section id="enter" className="story enter">
        <Tag id="enter" />
        <Logo variant="mark" decorative className="enter-mark" />
        <h2 data-reveal>From offset history to the next drilling decision.</h2>
        <p data-reveal>{PRODUCT.name} · {PRODUCT.subtitle}</p>
        <Link className="button primary large" to={enter}>{signedIn ? 'Open NWIS' : 'Enter NWIS'}</Link>
      </section>
    </main>
    <footer className="landing-footer"><Logo variant="horizontal" decorative /><p>{PRODUCT.context.join(' · ')}. {PRODUCT.positioning}. Demo data is synthetic (dataset_origin = synthetic_demo) and is not Oil India data. Advisory decision support only.</p></footer>
  </div>
}
