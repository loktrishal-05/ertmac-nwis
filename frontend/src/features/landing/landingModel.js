// eRTMAC-NWIS landing content model and small maths helpers. Pure and testable.
// Product facts only: design properties of the prototype, never invented field results or NPT savings.

export const PRODUCT = {
  name: 'eRTMAC-NWIS',
  subtitle: 'Nearby Wells Intelligence System',
  description: 'AI-Powered Offset-Well Knowledge & Decision Support for Drilling Operations',
  context: ['SIH26121', 'Oil India Limited', 'Smart Automation'],
  positioning: 'Designed for Oil India / eRTMAC workflows',
}

export const FACTS = [
  [7, 'hazard classes assessed separately'],
  [3, 'look-ahead windows · 50 / 100 / 150 m'],
  [6, 'similarity components shown per offset'],
  [0, 'automatic rig or equipment actions'],
]

export const STORY = [
  { id: 'hero', tag: 'NW-00' },
  { id: 'sources', tag: 'SRC-01' },
  { id: 'unify', tag: 'MEM-01' },
  { id: 'workflow', tag: 'FLOW-02' },
  { id: 'reports', tag: 'DDR-01' },
  { id: 'nearby', tag: 'GEO-02' },
  { id: 'correlation', tag: 'TVD-03' },
  { id: 'telemetry', tag: 'RPL-04' },
  { id: 'lookahead', tag: 'RISK-05' },
  { id: 'evidence', tag: 'CITE-06' },
  { id: 'architecture', tag: 'SYS-07' },
  { id: 'enter', tag: 'GO-08' },
]

// Illustrative scenario on the landing page (synthetic, mirrors the demo dataset; not Oil India data).
export const SCENARIO = {
  record: [['event_type', 'stuck_pipe'], ['depth', '2,529 m MD · 2,455 m TVD'], ['formation', 'TIPAM_A'], ['mitigation', 'pipe-release pill, jarring'], ['outcome', 'freed after 9 h · 14 h NPT'], ['source', 'DDR-OFF04 · page 2'], ['confidence', '0.91 · verified']],
  offsets: [
    { id: 'OFF-02', x: 46, y: 78, note: 'closest · across fault', rank: 6 },
    { id: 'OFF-12', x: 62, y: 22, note: 'never reached interval', rank: 5 },
    { id: 'OFF-03', x: 22, y: 30, rank: 4 },
    { id: 'OFF-04', x: 118, y: 44, top: true, rank: 1 },
    { id: 'OFF-09', x: 104, y: 104, top: true, rank: 2 },
    { id: 'OFF-07', x: 128, y: -30, rank: 3 },
  ],
  risks: [['Stuck pipe', 0.72, 0.78, 'rising'], ['Mud loss', 0.46, 0.68, 'rising'], ['Kick / overpressure', 0.11, 0.41, 'steady']],
}

// The five knowledge sources NWIS unifies into one offset-well memory (landing convergence scene).
export const SOURCES = [
  { id: 'ddr', label: 'Daily drilling reports', short: 'DDR', detail: 'Operations, depths, NPT, mitigations', color: '#35d7e8' },
  { id: 'wcr', label: 'Well completion reports', short: 'WCR', detail: 'Casing, cement, outcomes', color: '#3d8bff' },
  { id: 'tops', label: 'Formation tops', short: 'Tops', detail: 'Stratigraphy by TVD / TVDSS', color: '#2fe0a4' },
  { id: 'surveys', label: 'Trajectory surveys', short: 'Surveys', detail: 'MD, TVD, inclination, azimuth', color: '#f2a93b' },
  { id: 'telemetry', label: 'Drilling telemetry', short: 'Telemetry', detail: 'Replay: torque, ROP, SPP, hookload', color: '#8b6cff' },
]

export const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value))
export const easeInOut = t => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
export const smoothstep = (edge0, edge1, x) => { const t = clamp((x - edge0) / (edge1 - edge0)); return t * t * (3 - 2 * t) }

// DPR-aware backing store, capped at 2x to bound GPU memory.
export function canvasSize(cssWidth, cssHeight, devicePixelRatio = 1) {
  const dpr = Math.min(2, Math.max(1, devicePixelRatio || 1))
  return { width: Math.max(1, Math.round(cssWidth * dpr)), height: Math.max(1, Math.round(cssHeight * dpr)), dpr }
}

// Deterministic PRNG so every visitor sees the same scene.
export function seeded(seed) {
  let state = seed >>> 0
  return () => { state = (state + 0x6d2b79f5) >>> 0; let t = state; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

// Convergence particles: each source starts as a coloured cluster on a pentagon and settles onto one shared ring.
export function createParticles(perSource = 70, seed = 20260930) {
  const random = seeded(seed)
  return SOURCES.flatMap((source, sourceIndex) => Array.from({ length: perSource }, (_, index) => ({
    source: sourceIndex, color: source.color, homeAngle: (sourceIndex / SOURCES.length) * Math.PI * 2 - Math.PI / 2,
    jitterX: (random() - 0.5) * 0.18, jitterY: (random() - 0.5) * 0.18,
    ringAngle: ((sourceIndex * perSource + index) / (SOURCES.length * perSource)) * Math.PI * 2,
    delay: random() * 0.25, size: 0.6 + random() * 1.6,
  })))
}

// Unit-space particle position: scattered clusters (progress 0) converge onto the core ring (progress 1).
export function particlePosition(particle, progress) {
  const t = easeInOut(clamp((progress - particle.delay) / 0.7))
  const homeX = Math.cos(particle.homeAngle) * 0.36 + particle.jitterX
  const homeY = Math.sin(particle.homeAngle) * 0.36 + particle.jitterY
  const ringX = Math.cos(particle.ringAngle) * 0.2
  const ringY = Math.sin(particle.ringAngle) * 0.2
  return { x: homeX + (ringX - homeX) * t, y: homeY + (ringY - homeY) * t, t }
}
