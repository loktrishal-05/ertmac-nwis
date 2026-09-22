import { useCallback, useEffect, useRef, useState } from 'react'
import { apiRequest } from '../services/api.js'

export function useRequest() {
  const [state, setState] = useState({ data: null, error: null, loading: false })
  const active = useRef(null)
  useEffect(() => () => active.current?.abort(), [])
  const run = useCallback(async (path, options) => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setState({ data: null, error: null, loading: true })
    try {
      const data = await apiRequest(path, { ...options, signal: controller.signal })
      if (!controller.signal.aborted) setState({ data, error: null, loading: false })
      return controller.signal.aborted ? null : data
    } catch (error) {
      if (!controller.signal.aborted) setState({ data: null, error, loading: false })
      return null
    }
  }, [])
  const reset = useCallback(() => {
    active.current?.abort()
    setState({ data: null, error: null, loading: false })
  }, [])
  return { ...state, run, reset }
}

export function useResource(path) {
  const request = useRequest()
  const { run } = request
  const [version, setVersion] = useState(0)
  useEffect(() => { if (path) run(path) }, [path, run, version])
  return { ...request, refresh: () => setVersion(v => v + 1) }
}
