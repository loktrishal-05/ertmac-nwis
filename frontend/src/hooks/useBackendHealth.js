import { useEffect, useState } from 'react'
import { getBackendHealth } from '../services/api.js'

export function useBackendHealth() {
  const [health, setHealth] = useState({ status: 'Checking', checkedAt: null })

  useEffect(() => {
    let disposed = false
    let pollTimer
    let controller

    async function check() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5000)
      let status = 'Disconnected'
      try {
        await getBackendHealth(controller.signal)
        status = 'Connected'
      } catch {
        // Failed, malformed, and timed-out responses all mean unavailable.
      } finally {
        clearTimeout(timeout)
      }
      if (!disposed) {
        setHealth({ status, checkedAt: new Date() })
        pollTimer = setTimeout(check, 15000)
      }
    }

    check()
    return () => {
      disposed = true
      clearTimeout(pollTimer)
      controller?.abort()
    }
  }, [])

  return health
}
