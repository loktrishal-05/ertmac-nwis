// Single shared in-browser Qwen worker (Knowledge Search summary + NWIS assistant), so the model loads once.
let worker = null
const listeners = new Map()

export const browserLlmSupported = () => !!globalThis.navigator?.gpu && typeof Worker !== 'undefined'

// onEvent receives { type: 'progress' | 'fallback' | 'ready' | 'token' | 'done' | 'error', ... }. Returns an unsubscribe.
export function askBrowserLlm(messages, onEvent, { maxTokens } = {}) {
  if (!worker) {
    worker = new Worker(new URL('./llmWorker.js', import.meta.url), { type: 'module' })
    worker.onmessage = ({ data }) => {
      listeners.get(data.id)?.(data)
      if (data.type === 'done' || data.type === 'error') listeners.delete(data.id)
    }
  }
  const id = crypto.randomUUID()
  listeners.set(id, onEvent)
  worker.postMessage({ id, messages, maxTokens })
  return () => listeners.delete(id) // the model stays loaded for the next request
}
