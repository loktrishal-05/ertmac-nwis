// Same-origin /api routing rule shared by the Vite proxy (and to be mirrored by any production reverse proxy).
// The backend has two route families:
//   • NWIS (SIH26121) routes are mounted under /api on the backend: /api/wells, /api/query, /api/audit, …
//   • shared/legacy routes live at the backend root: /auth/*, /health, /ready, /audit/verify, …
// The browser always calls /api/<path>; NWIS paths keep the prefix, everything else has it stripped once.
export const NWIS_ROUTE = /^\/api\/(?:(?:wells|events|query|assessments|advisories|terms|reports|ingest)(?:[/?#]|$)|audit(?:[?#]|$))/

export const rewriteApiPath = path => (NWIS_ROUTE.test(path) ? path : path.replace(/^\/api(?=\/|$)/, '') || '/')
