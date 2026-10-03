// Floating NWIS help assistant: text + voice, English / हिन्दी / தமிழ். Answers only questions about using the app.
// Curated answers are instant and work everywhere; "AI answers" optionally rephrases them with the in-browser Qwen.
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { AgentAvatar } from '../../components/ui.jsx'
import { useLanguage } from '../../language.js'
import { askBrowserLlm, browserLlmSupported } from '../nwis/browserLlm.js'
import { SPEECH_LOCALE, assistantMessages, respond } from './assistantModel.js'
import './assistant.css'

const Recognition = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition

function speak(text, lang) {
  const synth = globalThis.speechSynthesis
  if (!synth) return false
  synth.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = SPEECH_LOCALE[lang]
  utterance.voice = synth.getVoices().find(v => v.lang?.toLowerCase().startsWith(lang)) || null
  synth.speak(utterance)
  return true
}

export default function Assistant() {
  const { language } = useLanguage()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [useAi, setUseAi] = useState(false)
  const [listening, setListening] = useState(false)
  const [notice, setNotice] = useState('')
  const listRef = useRef(null)
  const unsubscribe = useRef(null)
  useEffect(() => () => { unsubscribe.current?.(); globalThis.speechSynthesis?.cancel() }, [])
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight }) }, [messages])

  const update = (id, patch) => setMessages(list => list.map(m => (m.id === id ? { ...m, ...patch } : m)))

  function send(text) {
    const question = text.trim()
    if (!question) return
    setInput('')
    const reply = respond(question, language)
    const id = crypto.randomUUID()
    setMessages(list => [...list, { id: `${id}-q`, role: 'user', text: question },
      { id, role: 'assistant', text: reply.text, lang: reply.lang, route: reply.route, source: 'help' }])
    if (reply.kind !== 'answer' || !useAi || !browserLlmSupported()) return
    let streamed = ''
    update(id, { pending: true })
    unsubscribe.current = askBrowserLlm(assistantMessages(question, reply), event => {
      if (event.type === 'token') { streamed += event.text; update(id, { text: streamed, source: 'ai', pending: false }) }
      if (event.type === 'progress' && event.total) update(id, { progress: Math.round((100 * event.loaded) / event.total) })
      if (event.type === 'done') update(id, { pending: false, progress: null, text: streamed.trim() || reply.text, source: streamed.trim() ? 'ai' : 'help' })
      if (event.type === 'error') update(id, { pending: false, progress: null, text: reply.text, source: 'help' }) // always fall back to the curated answer
    }, { maxTokens: 220 })
  }

  function listen() {
    if (!Recognition) { setNotice('Voice input is not available in this browser.'); return }
    const recognition = new Recognition()
    recognition.lang = SPEECH_LOCALE[language] || 'en-IN'
    recognition.interimResults = false
    recognition.onresult = event => send(event.results[0][0].transcript)
    recognition.onerror = () => setNotice('Voice input is not available in this browser.')
    recognition.onend = () => setListening(false)
    setNotice('')
    setListening(true)
    recognition.start()
  }

  if (!open) return <button type="button" className="nw-assistant-fab" aria-label="Open assistant" title="NWIS assistant" onClick={() => setOpen(true)}><AgentAvatar size={34} /></button>

  return <section className="nw-assistant" role="dialog" aria-label="NWIS assistant">
    <header>
      <AgentAvatar size={26} /><strong>NWIS assistant</strong>
      <button type="button" className="ghost" aria-label="Close assistant" onClick={() => setOpen(false)}>✕</button>
    </header>
    <p className="nw-assistant-scope">I help only with using eRTMAC-NWIS: screens, data, risk, evidence and sign-in.</p>
    <ol className="nw-assistant-log" ref={listRef} aria-live="polite">
      {messages.map(m => <li key={m.id} className={`nw-msg nw-msg-${m.role}`}>
        <p translate="no">{m.text}</p>
        {m.role === 'assistant' && <div className="nw-msg-actions">
          {m.pending && <span className="muted small" role="status">{m.progress != null ? `Loading model · ${m.progress}%` : 'Thinking…'}</span>}
          {m.source === 'ai' && <span className="nw-badge">AI answer</span>}
          {m.route && <button type="button" className="ghost" onClick={() => navigate(m.route)}>Go to page</button>}
          <button type="button" className="ghost" onClick={() => speak(m.text, m.lang) || setNotice('No voice for this language on this device.')}>Read aloud</button>
        </div>}
      </li>)}
    </ol>
    {notice && <p className="muted small" role="status">{notice}</p>}
    <form onSubmit={event => { event.preventDefault(); send(input) }}>
      <input value={input} onChange={e => setInput(e.target.value)} maxLength={500} placeholder="Ask about using NWIS…" aria-label="Ask about using NWIS…" />
      {Recognition && <button type="button" className="ghost" aria-label="Speak" onClick={listen} disabled={listening}>{listening ? 'Listening…' : '🎤'}</button>}
      <button className="primary" disabled={!input.trim()}>Send</button>
    </form>
    {browserLlmSupported() && <label className="nw-assistant-ai"><input type="checkbox" checked={useAi} onChange={e => setUseAi(e.target.checked)} /> Use AI answers (Qwen, in your browser)</label>}
  </section>
}
