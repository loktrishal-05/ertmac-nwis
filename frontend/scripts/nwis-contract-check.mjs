// Checks a RUNNING NWIS backend against the frontend contract (src/features/nwis/contract.js). Read-only GETs plus one
// POST /query (evidence search, no side effects). Does not submit advisory reviews.
//
//   NWIS_API_URL=http://127.0.0.1:8000 NWIS_SESSION_COOKIE='<cookie header value>' npm run contract:check
//
// NWIS_API_URL is the backend root (the Vite proxy strips /api, so paths here have no /api prefix).
// NWIS_SESSION_COOKIE is copied from a signed-in browser session; no credentials are stored or invented.
import { validateContract } from '../src/features/nwis/contract.js'

const base = (process.env.NWIS_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
const headers = { Accept: 'application/json', ...(process.env.NWIS_SESSION_COOKIE ? { Cookie: process.env.NWIS_SESSION_COOKIE } : {}) }
let failures = 0

async function call(method, path, body) {
  const response = await fetch(base + path, { method, headers: { ...headers, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined })
  const data = await response.json().catch(() => null)
  return { status: response.status, data }
}

async function check(label, contract, method, path, body) {
  try {
    const { status, data } = await call(method, path, body)
    if (status < 200 || status >= 300) { failures += 1; console.log(`FAIL ${label} ${method} ${path} → HTTP ${status} ${JSON.stringify(data?.detail ?? '').slice(0, 120)}`); return data }
    const problems = validateContract(contract, data)
    const origin = data?.dataset_origin ?? (Array.isArray(data) ? data[0]?.dataset_origin : data?.items?.[0]?.dataset_origin)
    if (problems.length) { failures += 1; console.log(`FAIL ${label} ${method} ${path}`); problems.slice(0, 15).forEach(p => console.log(`     - ${p}`)) }
    else console.log(`PASS ${label} ${method} ${path}${origin ? ` (dataset_origin=${origin})` : ''}`)
    return data
  } catch (error) {
    failures += 1
    console.log(`FAIL ${label} ${method} ${path} → ${error.message}`)
    return null
  }
}

const health = await call('GET', '/health').catch(error => ({ status: 0, data: { error: error.message } }))
console.log(`health: HTTP ${health.status} status=${health.data?.status} service=${health.data?.service ?? '—'} (frontend accepts status ok|healthy|up)`)
const wells = await check('wells', 'wellList', 'GET', '/wells?limit=200')
const list = Array.isArray(wells) ? wells : wells?.items || []
const active = process.env.NWIS_WELL_ID || list.find(w => w.role === 'active' || w.status === 'drilling')?.id || list[0]?.id
if (!active) { console.log('No well id available; set NWIS_WELL_ID.'); process.exit(1) }
const id = encodeURIComponent(active)
await check('well', 'well', 'GET', `/wells/${id}`)
for (const radius of [2, 5, 10, 20]) await check(`nearby ${radius} km`, 'nearby', 'GET', `/wells/${id}/nearby?radius_km=${radius}`)
await check('correlation', 'correlation', 'GET', `/wells/${id}/correlation?lookahead_m=100&depth_ref=tvd`)
await check('events', 'eventList', 'GET', '/events?limit=100')
for (const lookahead of [50, 100, 150]) await check(`risk ${lookahead} m`, 'risk', 'GET', `/wells/${id}/risk?lookahead_m=${lookahead}`)
await check('telemetry', 'telemetry', 'GET', `/wells/${id}/telemetry?window_s=600`)
await check('query', 'query', 'POST', '/query', { query: 'Show stuck-pipe incidents in Tipam between 2400-2700 m TVD', well_id: active, mode: 'nwis_evidence', request_id: crypto.randomUUID() })
await check('advisories', 'advisoryList', 'GET', `/advisories?well_id=${id}`)
await check('audit', 'auditList', 'GET', '/audit/log?limit=100')
console.log(failures ? `\n${failures} endpoint(s) do not satisfy the frontend contract.` : '\nAll endpoints satisfy the frontend contract.')
process.exit(failures ? 1 : 0)
