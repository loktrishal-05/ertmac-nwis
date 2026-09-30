import { useEffect, useMemo, useRef } from 'react'
import { useResource } from '../../hooks/useApi.js'
import { paths } from './nwisModel.js'
import { adaptEventList, adaptNearby, adaptRisk } from './adapters.js'
import { useNwis } from './NwisContext.jsx'

// Every NWIS read goes through an adapter: `data` is the canonical domain shape, never the raw response.
// `adapt` must be a stable module-level function.
export function useNwisResource(path, adapt) {
  const request = useResource(path)
  const data = useMemo(() => (request.data == null ? null : adapt(request.data)), [request.data, adapt])
  return { ...request, data }
}

// Radius query for a well (default: the active context well). The backend filters and scores; we only pass parameters.
export function useNearby({ filters = {}, radiusKm, wellId } = {}) {
  const context = useNwis()
  const id = wellId ?? context.wellId
  const request = useNwisResource(id ? paths.nearby(id, { radius_km: radiusKm ?? context.radiusKm, ...filters }) : null, adaptNearby)
  const ids = request.data?.items.map(o => o.id) ?? []
  const history = useEventsFor(ids.length ? ids : null)
  // B2 matches are flat (no coordinates, no event counts): attach the catalogue record by id for map placement, and count
  // the offsets' recorded events from /api/events. Counts stay null (unknown) until events load, or if the page was truncated.
  const offsets = useMemo(() => {
    const byId = new Map(context.wellList.map(w => [w.id, w]))
    const complete = history.request.data && !history.request.data.has_more
    const counts = {}
    if (complete) for (const e of history.events) (counts[e.well_id] ??= {})[e.type] = (counts[e.well_id]?.[e.type] ?? 0) + 1
    return (request.data?.items ?? []).map(o => ({ ...o, well: byId.get(o.id) ?? o.well, eventCounts: o.eventCounts ?? (complete ? counts[o.id] ?? {} : null) }))
  }, [request.data, context.wellList, history.request.data, history.events])
  return { request, offsets }
}

export function useRisk(wellId, lookaheadOverride) {
  const context = useNwis()
  const id = wellId ?? context.wellId
  const request = useNwisResource(id ? paths.risk(id, lookaheadOverride ?? context.lookahead) : null, adaptRisk)
  return { request, hazards: request.data?.hazards ?? [] }
}

// B2 filters events by a single well_id (limit ≤ 100). Several wells: one bounded page, filtered by id here.
export function useEventsFor(wellIds, extra = {}) {
  const key = wellIds?.join(',')
  const single = wellIds?.length === 1 ? wellIds[0] : undefined
  const request = useNwisResource(key ? paths.events({ ...extra, well_id: single, limit: 100 }) : null, adaptEventList)
  const events = useMemo(() => {
    const wanted = new Set(key ? key.split(',') : [])
    return (request.data?.items ?? []).filter(e => wanted.has(e.well_id))
  }, [request.data, key])
  return { request, events }
}

// Refresh while the tab is visible (live/replay telemetry). Bounded interval; no work in hidden tabs.
export function usePolling(refresh, ms) {
  const latest = useRef(refresh)
  useEffect(() => { latest.current = refresh })
  useEffect(() => {
    if (!ms) return undefined
    const id = setInterval(() => { if (!document.hidden) latest.current() }, ms)
    return () => clearInterval(id)
  }, [ms])
}
