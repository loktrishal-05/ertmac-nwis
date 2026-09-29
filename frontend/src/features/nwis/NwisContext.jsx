import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useResource } from '../../hooks/useApi.js'
import { listOf, paths } from './nwisModel.js'
import { adaptWellList } from './adapters.js'

// Analyst context shared by every NWIS screen: which well is active, the offset radius, the look-ahead window and
// session-only offset preferences (pin / exclude / compare). Kept in sessionStorage; never sent as ground truth.
const DEFAULTS = { wellId: null, radiusKm: 5, lookahead: 100, pinned: [], excluded: [], compare: [] }
const KEY = 'nwis-analyst-context'
const NwisContext = createContext(null)

function load() {
  try { return { ...DEFAULTS, ...JSON.parse(sessionStorage.getItem(KEY) || '{}') } } catch { return DEFAULTS }
}

export function NwisProvider({ children }) {
  const wellsRequest = useResource(paths.wells())
  const wellsData = useMemo(() => (wellsRequest.data == null ? null : adaptWellList(wellsRequest.data)), [wellsRequest.data])
  const wells = { ...wellsRequest, data: wellsData }
  const [state, setState] = useState(load)
  useEffect(() => { try { sessionStorage.setItem(KEY, JSON.stringify(state)) } catch { /* Preference only. */ } }, [state])
  const list = listOf(wells.data)
  // Default to the well the backend marks as actively drilling; an explicit choice wins while it still exists.
  const fallback = list.find(w => w.role === 'active' || w.status === 'drilling')?.id ?? null
  const wellId = state.wellId && (!list.length || list.some(w => w.id === state.wellId)) ? state.wellId : fallback
  const set = useCallback(patch => setState(current => ({ ...current, ...patch })), [])
  const toggle = useCallback((key, id, limit) => setState(current => {
    const has = current[key].includes(id)
    const next = has ? current[key].filter(x => x !== id) : [...current[key], id].slice(-(limit || 50))
    return { ...current, [key]: next }
  }), [])
  // The wells request object changes identity each render, so the context value is not memoized.
  const value = { ...state, wellId, well: list.find(w => w.id === wellId) || null, wells, wellList: list, set, toggle }
  return <NwisContext.Provider value={value}>{children}</NwisContext.Provider>
}

export const useNwis = () => useContext(NwisContext)
