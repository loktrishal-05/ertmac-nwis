// Runs Qwen 3.5 entirely in the viewer's browser (WebGPU + ONNX). Nothing is sent to any server but the
// Hugging Face CDN for the one-time model download, which the browser caches for later visits.
import { AutoModelForCausalLM, AutoTokenizer, TextStreamer, env } from '@huggingface/transformers'
import { pickModels } from './browserLlmModel.js'

env.allowLocalModels = false
let loaded = null // { id, label, tokenizer, model }
let failure = null // a device that cannot run either model fails fast on later requests

async function load(post) {
  if (loaded) return loaded
  if (failure) throw failure
  try { return await loadFirstThatFits(post) } catch (error) { throw (failure = error) }
}

async function loadFirstThatFits(post) {
  const adapter = await globalThis.navigator?.gpu?.requestAdapter?.()
  if (!adapter) throw Object.assign(new Error('WebGPU is not available in this browser.'), { code: 'unsupported' })
  const dtype = adapter.features.has('shader-f16') ? 'q4f16' : 'q4'
  let lastError
  for (const choice of pickModels(globalThis.navigator?.deviceMemory)) {
    // Files register one by one, so a running sum of their totals jumps around; measure against the known size instead.
    const files = {}
    const progress_callback = p => {
      if (p.status !== 'progress') return
      files[p.file] = p.loaded
      const done = Object.values(files).reduce((a, b) => a + b, 0)
      post({ type: 'progress', label: choice.label, loaded: Math.min(done, choice.downloadGb * 0.99e9), total: choice.downloadGb * 1e9 })
    }
    try {
      post({ type: 'progress', label: choice.label, loaded: 0, total: 0 })
      const tokenizer = await AutoTokenizer.from_pretrained(choice.id)
      const model = await AutoModelForCausalLM.from_pretrained(choice.id, { dtype, device: 'webgpu', progress_callback })
      return (loaded = { ...choice, tokenizer, model })
    } catch (error) {
      lastError = error // usually out of GPU memory: fall back to the smaller model
      post({ type: 'fallback', from: choice.label })
    }
  }
  throw lastError
}

// One model, shared by every caller: requests run one at a time and every reply carries the request id.
let queue = Promise.resolve()
self.onmessage = ({ data }) => { queue = queue.then(() => handle(data)) }

async function handle({ id, messages, maxTokens = 384 }) {
  const post = message => self.postMessage({ ...message, id })
  try {
    const { label, tokenizer, model } = await load(post)
    post({ type: 'ready', label })
    const inputs = tokenizer.apply_chat_template(messages, { add_generation_prompt: true, return_dict: true, enable_thinking: false })
    const streamer = new TextStreamer(tokenizer, { skip_prompt: true, skip_special_tokens: true, callback_function: text => post({ type: 'token', text }) })
    await model.generate({ ...inputs, max_new_tokens: maxTokens, do_sample: false, streamer })
    post({ type: 'done', label })
  } catch (error) {
    post({ type: 'error', code: error.code || 'failed', message: String(error?.message || error) })
  }
}
