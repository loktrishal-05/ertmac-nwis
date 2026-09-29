// The Sovereign Core: raw WebGL, no dependencies. The approved mark is sampled into GPU particles that
// assemble out of a scattered "data nebula", breathe, part around the pointer and disperse as the visitor scrolls on.

const FLOOR_VS = `attribute vec2 aPos; varying vec2 vUv; void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`
const FLOOR_FS = `#extension GL_OES_standard_derivatives : enable
precision highp float;
varying vec2 vUv;
uniform float uTime; uniform float uAspect; uniform float uScroll; uniform vec2 uPointer;
float grid(vec2 p, float w) { vec2 g = abs(fract(p - 0.5) - 0.5) / fwidth(p); return 1.0 - min(min(g.x, g.y) / w, 1.0); }
void main() {
  vec2 uv = vUv; float horizon = 0.40 + uPointer.y * 0.015;
  vec3 col = vec3(0.0); float a = 0.0;
  float band = exp(-pow((uv.y - horizon) * 22.0, 2.0));
  col += vec3(0.20, 0.72, 0.86) * band * 0.3; a += band * 0.3;
  if (uv.y < horizon) {
    float depth = horizon - uv.y;
    float z = 0.28 / max(depth, 0.002);
    float x = (uv.x - 0.5 - uPointer.x * 0.02) * uAspect * z * 2.4;
    vec2 p = vec2(x, z + uTime * 0.35);
    float line = grid(p * 0.9, 1.1);
    float major = grid(p * 0.18, 1.4);
    float fade = smoothstep(0.0, 0.26, depth) * (1.0 - smoothstep(0.0, 1.0, depth * 1.15)) * (1.0 - uScroll * 0.8);
    float center = exp(-pow((uv.x - 0.5) * 1.6, 2.0));
    float glow = (line * 0.2 + major * 0.32) * fade * (0.45 + 0.55 * center);
    col += vec3(0.16, 0.62, 0.86) * glow; a += glow;
  }
  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));
}`

const POINT_VS = `precision highp float;
attribute vec3 aTarget; attribute vec3 aStart; attribute vec3 aColor; attribute float aSeed;
uniform float uTime; uniform float uAssemble; uniform float uScroll; uniform vec2 uPointer; uniform float uAspect;
uniform float uPixelRatio; uniform float uSize; uniform vec2 uTilt; uniform float uScale; uniform vec2 uOffset;
varying vec3 vColor; varying float vAlpha;
mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }
void main() {
  float k = clamp(uAssemble * 1.35 - aSeed * 0.35, 0.0, 1.0);
  k = k * k * (3.0 - 2.0 * k);
  vec3 p = mix(aStart, aTarget, k);
  float t = uTime;
  p += (1.0 - k * 0.85) * 0.05 * vec3(sin(t * 0.7 + aSeed * 40.0), cos(t * 0.6 + aSeed * 31.0), sin(t * 0.5 + aSeed * 17.0));
  p += k * 0.008 * vec3(sin(t * 1.6 + aSeed * 60.0), cos(t * 1.4 + aSeed * 50.0), 0.0);
  p += normalize(aStart + 0.0001) * uScroll * (1.2 + aSeed * 1.8);
  p = rotX(uTilt.y + 0.10) * rotY(uTilt.x + sin(t * 0.22) * 0.22) * p;
  float persp = 2.2 / (3.1 + uScroll * 1.2 - p.z);
  vec2 screen = p.xy * persp * uScale;
  screen.x /= uAspect;
  screen += uOffset;
  vec2 toPointer = screen - uPointer;
  vec2 metric = vec2(toPointer.x * uAspect, toPointer.y);
  float push = smoothstep(0.26, 0.0, length(metric)) * k * (1.0 - uScroll);
  screen += normalize(toPointer + 0.0001) * push * 0.07;
  gl_Position = vec4(screen, 0.0, 1.0);
  gl_PointSize = uSize * uPixelRatio * persp * (0.55 + aSeed * 0.9) * (1.0 + push * 1.5);
  vColor = aColor + push * vec3(0.35, 0.45, 0.5);
  vAlpha = (0.35 + 0.65 * k) * (0.55 + 0.45 * aSeed) * (1.0 - uScroll * 0.92);
}`
const POINT_FS = `precision highp float;
varying vec3 vColor; varying float vAlpha;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float a = exp(-dot(c, c) * 18.0) * vAlpha;
  gl_FragColor = vec4(vColor * a, a);
}`

function compile(gl, type, source) {
  const shader = gl.createShader(type)
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'shader compile failed')
  return shader
}
function link(gl, vs, fs) {
  const p = gl.createProgram()
  gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs))
  gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs))
  gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'program link failed')
  return p
}

// Deterministic PRNG so the nebula is identical on every visit.
export function prng(seed) {
  let s = seed >>> 0
  return () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

// Turn the mark's own pixels into particles: x/y from position, depth from luminance, colour from the artwork.
export function particlesFromPixels(pixels, resolution, count, seed = 20260929) {
  const candidates = []
  for (let y = 0; y < resolution; y += 1) for (let x = 0; x < resolution; x += 1) {
    const i = (y * resolution + x) * 4
    if (pixels[i + 3] > 70) candidates.push([x, y, pixels[i] / 255, pixels[i + 1] / 255, pixels[i + 2] / 255, pixels[i + 3] / 255])
  }
  const random = prng(seed)
  const n = candidates.length ? count : 0
  const target = new Float32Array(n * 3), start = new Float32Array(n * 3), color = new Float32Array(n * 3), seeds = new Float32Array(n)
  for (let k = 0; k < n; k += 1) {
    const [x, y, r, g, b, alpha] = candidates[Math.floor(random() * candidates.length)]
    const luma = 0.3 * r + 0.59 * g + 0.11 * b
    target.set([(x + random() - 0.5) / resolution * 2 - 1, 1 - (y + random() - 0.5) / resolution * 2, (luma - 0.45) * 0.42 + (random() - 0.5) * 0.05], k * 3)
    // Five loose clusters around the mark: SOPs, P&IDs, sensors, maintenance, operator knowledge.
    const cluster = Math.floor(random() * 5), angle = (cluster / 5) * Math.PI * 2 + (random() - 0.5) * 0.9
    const radius = 1.5 + random() * 1.4
    start.set([Math.cos(angle) * radius * 1.35, Math.sin(angle) * radius * 0.8, (random() - 0.5) * 2.4], k * 3)
    const boost = 1.15 + alpha * 0.25
    color.set([Math.min(1, r * boost), Math.min(1, g * boost), Math.min(1, b * boost)], k * 3)
    seeds[k] = random()
  }
  return { target, start, color, seed: seeds, count: n }
}

export function createHeroScene(canvas, image, { particles = 14000 } = {}) {
  const gl = canvas.getContext('webgl', { alpha: true, antialias: false, premultipliedAlpha: true, powerPreference: 'high-performance' })
  if (!gl || !gl.getExtension('OES_standard_derivatives')) return null
  const floor = link(gl, FLOOR_VS, FLOOR_FS)
  const points = link(gl, POINT_VS, POINT_FS)
  const quad = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, quad)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)

  const resolution = 200
  const sampler = document.createElement('canvas')
  sampler.width = sampler.height = resolution
  const sctx = sampler.getContext('2d', { willReadFrequently: true })
  sctx.drawImage(image, 0, 0, resolution, resolution)
  const data = particlesFromPixels(sctx.getImageData(0, 0, resolution, resolution).data, resolution, particles)

  const buffers = []
  for (const [name, array, size] of [['aTarget', data.target, 3], ['aStart', data.start, 3], ['aColor', data.color, 3], ['aSeed', data.seed, 1]]) {
    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, array, gl.STATIC_DRAW)
    buffers.push({ buffer, size, location: gl.getAttribLocation(points, name) })
  }
  const u = (p, name) => gl.getUniformLocation(p, name)
  const fu = { time: u(floor, 'uTime'), aspect: u(floor, 'uAspect'), scroll: u(floor, 'uScroll'), pointer: u(floor, 'uPointer') }
  const pu = Object.fromEntries(['uTime', 'uAssemble', 'uScroll', 'uPointer', 'uAspect', 'uPixelRatio', 'uSize', 'uTilt', 'uScale', 'uOffset'].map(n => [n, u(points, n)]))
  const floorPos = gl.getAttribLocation(floor, 'aPos')

  const state = { assemble: 0, scroll: 0, pointer: [0, 0], pointerTarget: [0, 0], scale: 0.5, offset: [0, 0], dpr: 1, width: 1, height: 1 }
  let frame = 0, running = false
  const born = performance.now()

  function resize(width, height, dpr) {
    Object.assign(state, { width, height, dpr })
    canvas.width = Math.max(1, Math.round(width * dpr))
    canvas.height = Math.max(1, Math.round(height * dpr))
    gl.viewport(0, 0, canvas.width, canvas.height)
    // Wide screens: the sculpture sits right of the headline. Narrow screens: centred above it.
    if (width / height > 1.15) { state.scale = Math.min(0.54, 0.28 + height / 2800); state.offset = [0.47, 0.05] }
    else {
      // Narrow screens: the sculpture lives in the top band of the real viewport so the headline and CTA fit below it.
      const viewport = Math.min(window.innerHeight || height, height)
      const top = 64, band = viewport * 0.38 - top
      const half = band * 0.46 // Half the sculpture's height in CSS pixels.
      state.scale = (half * 2) / ((2.2 / 3.1) * height)
      state.offset = [0, 1 - ((top + band / 2) / height) * 2]
    }
  }
  function draw(now) {
    const t = (now - born) / 1000
    state.pointer[0] += (state.pointerTarget[0] - state.pointer[0]) * 0.08
    state.pointer[1] += (state.pointerTarget[1] - state.pointer[1]) * 0.08
    const aspect = state.width / state.height
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.useProgram(floor)
    gl.bindBuffer(gl.ARRAY_BUFFER, quad)
    gl.enableVertexAttribArray(floorPos)
    gl.vertexAttribPointer(floorPos, 2, gl.FLOAT, false, 0, 0)
    gl.uniform1f(fu.time, t); gl.uniform1f(fu.aspect, aspect); gl.uniform1f(fu.scroll, state.scroll); gl.uniform2f(fu.pointer, state.pointer[0], state.pointer[1])
    gl.drawArrays(gl.TRIANGLES, 0, 3)
    gl.disableVertexAttribArray(floorPos)
    gl.blendFunc(gl.ONE, gl.ONE) // Additive: overlapping particles bloom like light, not paint.
    gl.useProgram(points)
    for (const { buffer, size, location } of buffers) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.enableVertexAttribArray(location)
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0)
    }
    gl.uniform1f(pu.uTime, t); gl.uniform1f(pu.uAssemble, state.assemble); gl.uniform1f(pu.uScroll, state.scroll)
    gl.uniform2f(pu.uPointer, state.pointer[0], state.pointer[1]); gl.uniform1f(pu.uAspect, aspect)
    gl.uniform1f(pu.uPixelRatio, state.dpr); gl.uniform1f(pu.uSize, Math.max(2.2, Math.min(4.2, state.height / 230)))
    gl.uniform2f(pu.uTilt, state.pointer[0] * 0.35, -state.pointer[1] * 0.22)
    gl.uniform1f(pu.uScale, state.scale); gl.uniform2f(pu.uOffset, state.offset[0], state.offset[1])
    gl.drawArrays(gl.POINTS, 0, data.count)
    for (const { location } of buffers) gl.disableVertexAttribArray(location)
  }
  function loop(now) { draw(now); frame = running ? requestAnimationFrame(loop) : 0 }

  return {
    resize,
    setAssemble(value) { state.assemble = value },
    setScroll(value) { state.scroll = value },
    setPointer(x, y) { state.pointerTarget = [x, y] },
    play() { if (!running) { running = true; frame = requestAnimationFrame(loop) } },
    pause() { running = false; cancelAnimationFrame(frame); frame = 0 },
    destroy() { running = false; cancelAnimationFrame(frame); gl.getExtension('WEBGL_lose_context')?.loseContext() },
  }
}
