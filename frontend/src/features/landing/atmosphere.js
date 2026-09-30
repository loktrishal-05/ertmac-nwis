// The landing's living backdrop: raw WebGL, no dependencies. Domain-warped smoke in brand navy and instrument
// cyan. Cursor movement pushes the smoke the way the hand moves; scroll lifts it, so the atmosphere runs unbroken
// from the hero to the footer.

const VS = `attribute vec2 aPos; varying vec2 vUv; void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`
const FS = `precision highp float;
varying vec2 vUv;
uniform vec2 uRes; uniform float uTime; uniform vec2 uPointer; uniform vec2 uDrift; uniform float uScroll;
float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float noise(vec2 p) { vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y); }
float fbm(vec2 p) { float v = 0.0, a = 0.5; mat2 m = mat2(1.6, 1.2, -1.2, 1.6); for (int i = 0; i < 5; i++) { v += a * noise(p); p = m * p; a *= 0.5; } return v; }
void main() {
  float aspect = uRes.x / uRes.y;
  vec2 p = vec2(vUv.x * aspect, vUv.y);
  float t = uTime * 0.045;
  // Smoke: scroll lifts it slower than the page (depth), cursor drift pushes it the way the hand moves.
  vec2 q = p * 1.45 + vec2(0.0, -uScroll * 0.32) - uDrift;
  vec2 w = vec2(fbm(q + vec2(t, -t * 0.6)), fbm(q + vec2(5.2, 1.3) - t));
  float smoke = fbm(q + 2.4 * w + vec2(t * 1.6, -t * 0.8));
  float body = smoothstep(0.32, 0.92, smoke);
  vec3 col = vec3(0.008, 0.047, 0.118);
  col += vec3(0.045, 0.17, 0.42) * body * 1.3;
  col += vec3(0.12, 0.46, 0.82) * pow(body, 2.4) * 0.8;
  col += vec3(0.08, 0.10, 0.32) * smoothstep(0.55, 0.95, w.x) * 0.35; // a cold indigo undertone in the folds
  // Soft light where the cursor is, strongest inside the smoke.
  vec2 d = (vUv - uPointer) * vec2(aspect, 1.0);
  col += vec3(0.10, 0.52, 0.72) * exp(-dot(d, d) * 5.5) * (0.07 + 0.3 * body);
  col *= 1.0 - 0.38 * length((vUv - vec2(0.5, 0.55)) * vec2(1.1, 1.25));
  col += (hash(gl_FragCoord.xy + fract(uTime)) - 0.5) / 128.0; // dither: no banding in the dark gradients
  gl_FragColor = vec4(col, 1.0);
}`

function program(gl) {
  const make = (type, source) => {
    const shader = gl.createShader(type)
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'shader compile failed')
    return shader
  }
  const p = gl.createProgram()
  gl.attachShader(p, make(gl.VERTEX_SHADER, VS))
  gl.attachShader(p, make(gl.FRAGMENT_SHADER, FS))
  gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'program link failed')
  return p
}

// Returns null when WebGL is unavailable; the CSS gradient on .landing is the fallback.
export function createAtmosphere(canvas, { still = false } = {}) {
  const gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, powerPreference: 'high-performance' })
  if (!gl) return null
  let prog
  try { prog = program(gl) } catch { return null }
  gl.useProgram(prog)
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
  const pos = gl.getAttribLocation(prog, 'aPos')
  gl.enableVertexAttribArray(pos)
  gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0)
  const u = Object.fromEntries(['uRes', 'uTime', 'uPointer', 'uDrift', 'uScroll'].map(n => [n, gl.getUniformLocation(prog, n)]))

  // Pointer in 0..1 (y up). Velocity decays each frame, so the smoke glides on after the hand stops.
  const s = { pointer: [0.7, 0.45], target: [0.7, 0.45], velocity: [0, 0], drift: [0, 0], energy: 0, scroll: 0, lastScroll: window.scrollY }
  let frame = 0, running = false, last = performance.now(), time = 12

  function resize() {
    const scale = Math.min(window.devicePixelRatio || 1, 1) * 0.5 // Smoke is soft: half resolution is invisible and 4x cheaper.
    canvas.width = Math.max(1, Math.round(window.innerWidth * scale))
    canvas.height = Math.max(1, Math.round(window.innerHeight * scale))
    gl.viewport(0, 0, canvas.width, canvas.height)
    if (!running) draw()
  }
  function step(dt) {
    const scrollY = window.scrollY
    const scrollDelta = (scrollY - s.lastScroll) / Math.max(1, window.innerHeight)
    s.lastScroll = scrollY
    s.scroll += (scrollY / Math.max(1, window.innerHeight) - s.scroll) * 0.12
    s.velocity[1] += Math.max(-0.04, Math.min(0.04, scrollDelta)) * 0.5 // scrolling carries the smoke with the content; anchor jumps stay calm
    for (const i of [0, 1]) s.pointer[i] += (s.target[i] - s.pointer[i]) * 0.1
    const speed = Math.hypot(s.velocity[0], s.velocity[1])
    s.drift[0] += s.velocity[0] * 0.35
    s.drift[1] += s.velocity[1] * 0.35
    s.energy += (Math.min(1, speed * 25) - s.energy) * 0.08
    s.velocity[0] *= 0.9
    s.velocity[1] *= 0.9
    time += dt * (1 + s.energy * 1.5)
  }
  function draw() {
    gl.uniform2f(u.uRes, canvas.width, canvas.height)
    gl.uniform1f(u.uTime, time)
    gl.uniform2f(u.uPointer, s.pointer[0], s.pointer[1])
    gl.uniform2f(u.uDrift, s.drift[0], s.drift[1])
    gl.uniform1f(u.uScroll, s.scroll)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }
  function loop(now) {
    step(Math.min(0.05, (now - last) / 1000))
    last = now
    draw()
    frame = running ? requestAnimationFrame(loop) : 0
  }
  const onPointer = event => {
    const x = event.clientX / window.innerWidth, y = 1 - event.clientY / window.innerHeight
    s.velocity[0] += (x - s.target[0]) * 0.6
    s.velocity[1] += (y - s.target[1]) * 0.6
    s.target = [x, y]
  }
  if (!still) window.addEventListener('pointermove', onPointer, { passive: true })
  resize()

  return {
    resize,
    play() { if (still) { draw(); return } if (!running) { running = true; last = performance.now(); frame = requestAnimationFrame(loop) } },
    pause() { running = false; cancelAnimationFrame(frame); frame = 0 },
    // No loseContext(): a remount (StrictMode, fast refresh) reuses this canvas, and a lost context never comes back.
    destroy() { running = false; cancelAnimationFrame(frame); window.removeEventListener('pointermove', onPointer) },
  }
}
