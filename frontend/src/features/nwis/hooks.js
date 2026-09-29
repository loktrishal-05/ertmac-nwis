import { useEffect, useMemo, useRef, useState } from 'react'
import { useResource } from '../../hooks/useApi.js'
import { listOf, normalizeHazard, paths, rankedOffsets } from './nwisModel.js'
import { useNwis } from './NwisContext.jsx'

// Radius query for a well (default: the active context well). The backend filters and scores; we only pass parameters.
export function useNearby({ filters = {}, radiusKm, wellId } = {}) {
  const context = useNwis()
  const id = wellId ?? context.wellId
  const request = useResource(id ? paths.nearby(id, { radius_km: radiusKm ?? context.radiusKm, ...filters }) : null)
  const offsets = useMemo(() => rankedOffsets(request.data), [request.data])
  return { request, offsets }
}

export function useRisk(wellId) {
  const context = useNwis()
  const id = wellId ?? context.wellId
  const request = useResource(id ? paths.risk(id, context.lookahead) : null)
  const hazards = useMemo(() => (request.data?.hazards || []).map(normalizeHazard), [request.data])
  return { request, hazards }
}

export function useEventsFor(wellIds, extra = {}) {
  const key = wellIds?.join(',')
  const request = useResource(key ? paths.events({ well_id: key, ...extra }) : null)
  return { request, events: listOf(request.data) }
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
