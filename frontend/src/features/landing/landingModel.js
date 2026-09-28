// Landing content model and scroll/canvas maths. Pure and testable.

// Verified facts only (backend freeze 2f52117, release validation 2026-09). No invented industry statistics.
export const PRODUCT_FACTS = {
  hostedAiCalls: 0,
  localModels: 2,
  primaryModel: 'qwen3.5:9b',
  fastModel: 'qwen3.5:4b',
  languages: 3,
  workflowSteps: 5,
  evidenceSources: 5,
  backendTests: 890,
  benchmarkCases: 75,
  frozenBenchmarkFiles: 168,
  asOf: 'September 2026',
}

export const STORY = [
  { id: 'hero', tag: 'SW-00', title: 'Sovereign AI Workbench' },
  { id: 'scattered', tag: 'SRC-01', title: 'Industrial knowledge is scattered' },
  { id: 'unify', tag: 'CORE-02', title: 'One sovereign intelligence layer' },
  { id: 'workflow', tag: 'FLOW-03', title: 'Retrieve · Verify · Reason · Review · Approve' },
  { id: 'reveal', tag: 'UI-04', title: 'One governed workbench' },
  { id: 'pid', tag: 'PID-05', title: 'P&ID evidence, never proof of plant state' },
  { id: 'maintenance', tag: 'MNT-06', title: 'Maintenance and sensor intelligence' },
  { id: 'governance', tag: 'HITL-07', title: 'Humans approve. The chain remembers.' },
  { id: 'voice', tag: 'VOX-08', title: 'Speak locally. Review every identifier.' },
  { id: 'sovereignty', tag: 'SOV-09', title: 'Your hardware. Your boundary.' },
  { id: 'ecosystem', tag: 'GOV-10', title: 'Government ecosystem, accurately represented' },
  { id: 'enter', tag: 'GO-11', title: 'Enter Sovereign Workbench' },
]

export const SOURCES = [
  { id: 'sop', label: 'SOPs', detail: 'Procedures and manuals', color: '#35d7e8' },
  { id: 'pid', label: 'P&IDs', detail: 'Drawings and tags', color: '#3d8bff' },
  { id: 'sensors', label: 'Sensors', detail: 'Readings and trends', color: '#2fe0a4' },
  { id: 'maintenance', label: 'Maintenance', detail: 'Work orders and history', color: '#f2a93b' },
  { id: 'operators', label: 'Operator knowledge', detail: 'Shift notes and reports', color: '#8b6cff' },
]

export const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value))
export const easeInOut = t => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
export const smoothstep = (edge0, edge1, x) => { const t = clamp((x - edge0) / (edge1 - edge0)); return t * t * (3 - 2 * t) }

// Scroll progress (0..1) to a bounded frame index for image-sequence style rendering.
export function progressToFrame(progress, frameCount) {
  if (!Number.isFinite(progress) || frameCount < 1) return 0
  return Math.min(frameCount - 1, Math.max(0, Math.round(clamp(progress) * (frameCount - 1))))
}

// DPR-aware backing store, capped at 2x to bound GPU memory.
export function canvasSize(cssWidth, cssHeight, devicePixelRatio = 1) {
  const dpr = Math.min(2, Math.max(1, devicePixelRatio || 1))
  return { width: Math.max(1, Math.round(cssWidth * dpr)), height: Math.max(1, Math.round(cssHeight * dpr)), dpr }
}

// "object-fit: cover" for canvas drawing.
export function coverRect(sourceWidth, sourceHeight, targetWidth, targetHeight) {
  const scale = Math.max(targetWidth / sourceWidth, targetHeight / sourceHeight)
  const width = sourceWidth * scale
  const height = sourceHeight * scale
  return { x: (targetWidth - width) / 2, y: (targetHeight - height) / 2, width, height }
}

// Deterministic PRNG so every visitor sees the same convergence.
export function seeded(seed) {
  let state = seed >>> 0
  return () => { state = (state + 0x6d2b79f5) >>> 0; let t = state; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

export function createParticles(perSource = 60, seed = 20260929) {
  const random = seeded(seed)
  return SOURCES.flatMap((source, sourceIndex) => Array.from({ length: perSource }, (_, index) => {
    const angle = (sourceIndex / SOURCES.length) * Math.PI * 2 - Math.PI / 2
    return { source: sourceIndex, color: source.color, homeAngle: angle,
      jitterX: (random() - 0.5) * 0.18, jitterY: (random() - 0.5) * 0.18,
      ringAngle: ((sourceIndex * perSource + index) / (SOURCES.length * perSource)) * Math.PI * 2,
      delay: random() * 0.25, size: 0.6 + random() * 1.6 }
  }))
}

// Unit-space particle position: scattered clusters (0) converge onto the core ring (1).
export function particlePosition(particle, progress) {
  const t = easeInOut(clamp((progress - particle.delay) / 0.7))
  const homeX = Math.cos(particle.homeAngle) * 0.36 + particle.jitterX
  const homeY = Math.sin(particle.homeAngle) * 0.36 + particle.jitterY
  const ringX = Math.cos(particle.ringAngle) * 0.16
  const ringY = Math.sin(particle.ringAngle) * 0.16
  return { x: homeX + (ringX - homeX) * t, y: homeY + (ringY - homeY) * t, t }
}
