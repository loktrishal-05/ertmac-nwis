import { useEffect, useMemo, useRef, useState } from 'react'
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
  return { request, offsets: request.data?.items ?? [] }
}

export function useRisk(wellId, lookaheadOverride) {
  const context = useNwis()
  const id = wellId ?? context.wellId
  const request = useNwisResource(id ? paths.risk(id, lookaheadOverride ?? context.lookahead) : null, adaptRisk)
  return { request, hazards: request.data?.hazards ?? [] }
}

export function useEventsFor(wellIds, extra = {}) {
  const key = wellIds?.join(',')
  const request = useNwisResource(key ? paths.events({ well_id: key, ...extra }) : null, adaptEventList)
  return { request, events: request.data?.items ?? [] }
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

// Wall clock for freshness labels, ticking at a bounded interval (render stays pure).
export function useNow(ms = 10000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(id)
  }, [ms])
  return now
}
