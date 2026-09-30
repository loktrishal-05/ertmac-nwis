// Subsurface section scene (Canvas 2D, no dependencies): formation bands, offset-well trajectories descending from
// surface locations, historical events pulsing at the equivalent interval, and the active well drilling toward a
// look-ahead window. Illustrative only; no real well data. Deterministic, DPR-capped, pauses when hidden.
import { seeded } from './landingModel.js'

const LAYERS = [0.3, 0.42, 0.55, 0.68, 0.82] // formation tops as fractions of height
const BAND_ALPHA = [0.05, 0.085, 0.06, 0.1, 0.07]
const ease = t => 1 - (1 - Math.min(1, Math.max(0, t))) ** 3

export function createSubsurface(canvas, { still = false, activeX = 0.64, maxDpr = 1.75 } = {}) {
  const ctx = canvas.getContext?.('2d')
  if (!ctx) return null
  const random = seeded(26121)
  const wells = Array.from({ length: 10 }, (_, i) => ({
    x: 0.05 + i * 0.1 + (random() - 0.5) * 0.05, dev: (random() - 0.5) * 0.2, depth: 0.62 + random() * 0.3,
    delay: 0.2 + random() * 1.2, event: i % 3 === 1 ? 2 : i % 4 === 0 ? 3 : null,
  })).filter(w => Math.abs(w.x - activeX) > 0.06)
  let width = 1, height = 1, frame = 0, running = false, start = 0, scroll = 0, px = 0

  const layerY = (k, x, t) => height * (LAYERS[k] - scroll * 0.06) + Math.sin(x * 0.006 + k * 1.7 + t * 0.00015) * height * 0.012 + x * (k % 2 ? 0.018 : -0.012)
  const path = (x0, dev, depth, p) => { // quadratic trajectory sampled to progress p
    const pts = []
    const x1 = (x0 + dev) * width, y0 = height * (0.2 - scroll * 0.06), y1 = height * (depth - scroll * 0.06), cx = x0 * width, cy = (y0 + y1) * 0.55
    for (let i = 0; i <= 40 * p; i++) { const s = i / 40; pts.push([(1 - s) ** 2 * x0 * width + 2 * (1 - s) * s * cx + s * s * x1, (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y1]) }
    return pts
  }
  const stroke = pts => { if (pts.length < 2) return; ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke() }
  const crossing = (pts, k, t) => pts.find(([x, y]) => y >= layerY(k, x, t) + 14)

  function draw(now) {
    frame = 0
    const t = still ? 1e5 : now - start
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    const dpr = canvas.width / width
    ctx.setTransform(dpr, 0, 0, dpr, px * 8 * dpr, 0)
    // Formation bands and tops.
    for (let k = 0; k < LAYERS.length; k++) {
      ctx.beginPath()
      for (let x = -20; x <= width + 20; x += 24) ctx.lineTo(x, layerY(k, x, t))
      for (let x = width + 20; x >= -20; x -= 24) ctx.lineTo(x, k + 1 < LAYERS.length ? layerY(k + 1, x, t) : height + 20)
      ctx.fillStyle = `rgba(96, 150, 210, ${BAND_ALPHA[k]})`
      ctx.fill()
      ctx.beginPath()
      for (let x = -20; x <= width + 20; x += 24) ctx.lineTo(x, layerY(k, x, t))
      ctx.strokeStyle = 'rgba(143, 200, 240, 0.2)'
      ctx.lineWidth = 1
      ctx.setLineDash(k === 3 ? [5, 5] : [])
      ctx.stroke()
    }
    ctx.setLineDash([])
    // Surface datum.
    const surface = height * (0.2 - scroll * 0.06)
    ctx.strokeStyle = 'rgba(200, 225, 250, 0.22)'
    ctx.beginPath(); ctx.moveTo(0, surface); ctx.lineTo(width, surface); ctx.stroke()
    // Offset wells: trajectories draw in, historical events pulse where they crossed the analog interval.
    ctx.lineWidth = 1.4
    for (const w of wells) {
      const p = ease((t / 1000 - w.delay) / 2.2)
      const pts = path(w.x, w.dev, w.depth, p)
      ctx.strokeStyle = 'rgba(170, 196, 232, 0.38)'
      stroke(pts)
      ctx.fillStyle = 'rgba(200, 225, 250, 0.6)'
      ctx.fillRect(w.x * width - 3, surface - 3, 6, 6)
      if (w.event != null && p > 0.95) {
        const hit = crossing(pts, w.event, t)
        if (hit) {
          const pulse = (Math.sin(t * 0.003 + w.x * 10) + 1) / 2
          ctx.fillStyle = `rgba(242, 169, 59, ${0.12 + pulse * 0.14})`
          ctx.beginPath(); ctx.arc(hit[0], hit[1], 9 + pulse * 6, 0, Math.PI * 2); ctx.fill()
          ctx.fillStyle = '#f2a93b'
          ctx.beginPath(); ctx.arc(hit[0], hit[1], 3.2, 0, Math.PI * 2); ctx.fill()
        }
      }
    }
    // Active well: drills toward the analog interval; the look-ahead window glows ahead of the bit.
    const drill = ease((t / 1000 - 0.9) / 3.4)
    const active = path(activeX, 0.07, 0.5, Math.max(0.02, drill))
    ctx.strokeStyle = 'rgba(53, 215, 232, 0.95)'
    ctx.lineWidth = 2.6
    ctx.shadowColor = 'rgba(53, 215, 232, 0.7)'
    ctx.shadowBlur = 12
    stroke(active)
    ctx.shadowBlur = 0
    const bit = active.at(-1)
    if (bit && drill > 0.6) {
      // Look-ahead window: continue along the bit's current heading.
      const prev = active.at(-3) || active[0]
      const dx = bit[0] - prev[0], dy = bit[1] - prev[1], len = Math.hypot(dx, dy) || 1, reach = height * 0.09
      ctx.setLineDash([4, 5]); ctx.strokeStyle = `rgba(242, 169, 59, ${0.5 + 0.3 * Math.sin(t * 0.004)})`; ctx.lineWidth = 3
      stroke([bit, [bit[0] + (dx / len) * reach, bit[1] + (dy / len) * reach]]); ctx.setLineDash([])
    }
    if (bit) {
      const glow = ctx.createRadialGradient(bit[0], bit[1], 0, bit[0], bit[1], 26)
      glow.addColorStop(0, 'rgba(160, 245, 255, 0.9)'); glow.addColorStop(1, 'rgba(53, 215, 232, 0)')
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(bit[0], bit[1], 26, 0, Math.PI * 2); ctx.fill()
      ctx.fillStyle = 'rgba(232, 244, 252, 0.85)'
      ctx.font = '600 11px system-ui, sans-serif'
      ctx.fillText('ACTIVE-01', activeX * width + 10, surface - 10)
    }
    ctx.fillStyle = '#35d7e8'; ctx.fillRect(activeX * width - 4, surface - 4, 8, 8)
    if (running && !still) frame = requestAnimationFrame(draw)
  }

  return {
    resize(cssWidth, cssHeight) {
      width = Math.max(1, cssWidth); height = Math.max(1, cssHeight)
      const dpr = Math.min(maxDpr, window.devicePixelRatio || 1)
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr)
      if (!frame) frame = requestAnimationFrame(draw)
    },
    play() { if (still || running) return; running = true; if (!start) start = performance.now(); if (!frame) frame = requestAnimationFrame(draw) },
    pause() { running = false; cancelAnimationFrame(frame); frame = 0 },
    setScroll(value) { scroll = value; if (!running && !frame) frame = requestAnimationFrame(draw) },
    setPointer(x) { px = x },
    destroy() { running = false; cancelAnimationFrame(frame) },
  }
}
