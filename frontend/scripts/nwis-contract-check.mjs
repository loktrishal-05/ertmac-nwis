// Checks a RUNNING NWIS backend against the frontend contract (src/features/nwis/contract.js). Read-only GETs plus one
// POST /api/query (evidence search; the backend records a knowledge_query audit entry). Does not submit advisory reviews.
//
//   NWIS_API_URL=http://127.0.0.1:8011 NWIS_SESSION_COOKIE='<cookie header value>' npm run contract:check
//
// NWIS_API_URL is the backend root. NWIS routes live under /api; /health stays at the root (see src/services/apiRoutes.js).
// The session user must have accepted the NWIS advisory terms (POST /api/terms/accept), or every NWIS route returns 403.
// NWIS_SESSION_COOKIE is copied from a signed-in browser session; no credentials are stored or invented.
import { validateContract } from '../src/features/nwis/contract.js'

const base = (process.env.NWIS_API_URL || 'http://127.0.0.1:8011').replace(/\/+$/, '')
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
await check('terms', 'terms', 'GET', '/api/terms')
const wells = await check('wells', 'wellList', 'GET', '/api/wells?limit=100')
const active = process.env.NWIS_WELL_ID || wells?.items?.find(w => w.status === 'ACTIVE')?.id || wells?.items?.[0]?.id
if (!active) { console.log('No well id available; set NWIS_WELL_ID.'); process.exit(1) }
const id = encodeURIComponent(active)
await check('well', 'well', 'GET', `/api/wells/${id}`)
await check('formations', 'formationList', 'GET', `/api/wells/${id}/formations?limit=100`)
for (const radius of [2, 5, 10, 20]) await check(`nearby ${radius} km`, 'nearby', 'GET', `/api/wells/${id}/nearby?radius_km=${radius}&limit=100`)
await check('correlation', 'correlation', 'GET', `/api/wells/${id}/correlation?lookahead_m=100`)
await check('events', 'eventList', 'GET', '/api/events?limit=100')
let risk100 = null
for (const lookahead of [50, 100, 150]) { const data = await check(`risk ${lookahead} m`, 'risk', 'GET', `/api/wells/${id}/risk?lookahead_m=${lookahead}`); if (lookahead === 100) risk100 = data }
const assessmentId = risk100?.hazards?.[0]?.assessment_id
if (assessmentId) {
  const { status } = await call('GET', `/api/assessments/${encodeURIComponent(assessmentId)}`)
  if (status === 404) console.log('SKIP assessment: not recorded yet (POST /api/wells/{id}/assess persists it)')
  else await check('assessment', 'assessment', 'GET', `/api/assessments/${encodeURIComponent(assessmentId)}`)
}
await check('telemetry', 'telemetry', 'GET', `/api/wells/${id}/telemetry?limit=1000`)
await check('query', 'query', 'POST', '/api/query', { query: 'Show stuck-pipe incidents in Tipam between 2400-2700 m TVD', well_id: active, mode: 'nwis_evidence', request_id: crypto.randomUUID() })
await check('advisories', 'advisoryList', 'GET', '/api/advisories?limit=100')
await check('audit', 'auditList', 'GET', '/api/audit?limit=100')
console.log(failures ? `\n${failures} endpoint(s) do not satisfy the frontend contract.` : '\nAll endpoints satisfy the frontend contract.')
process.exit(failures ? 1 : 0)
