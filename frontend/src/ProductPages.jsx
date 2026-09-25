import { useEffect, useRef, useState } from 'react'
import { useRequest, useResource } from './hooks/useApi.js'
import { ApiState, DataView } from './WorkspacePages.jsx'
import { languages, useLanguage } from './language.js'

export function LanguageSelector() {
  const { language, setLanguage, t } = useLanguage()
  return <label>{t('Language')}<select value={language} onChange={e => setLanguage(e.target.value)}>{Object.entries(languages).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
}

export function VoiceAvailability({ status }) {
  const { t } = useLanguage()
  return status?.stt === 'configured_unverified' ? <p>{t('Review the transcript and technical identifiers before submitting.')}</p> : <p>{t('Voice unavailable; text mode remains available.')}</p>
}

export function VoiceControls({ user, onTranscript, result }) {
  const { language, t } = useLanguage()
  const status = useResource(user ? '/product/status' : null)
  const request = useRequest()
  const recorder = useRef(null)
  const timer = useRef(null)
  const mounted = useRef(true)
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState('')
  const [audio, setAudio] = useState(null)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; clearTimeout(timer.current); recorder.current?.stream.getTracks().forEach(track => track.stop()); if (recorder.current?.state === 'recording') recorder.current.stop() }
  }, [])
  async function transcribe(blob) {
    if (!blob || blob.size > 4 * 1024 * 1024) { setError('Audio must be at most 4 MiB.'); return }
    const reader = new FileReader()
    reader.onload = async () => {
      if (!mounted.current) return
      const data = await request.run('/voice/transcribe', { method: 'POST', timeout: 130000,
        body: { audio_base64: reader.result.split(',')[1], mime_type: blob.type.split(';')[0], input_language: language } })
      if (data?.status === 'ok') onTranscript(data.text)
    }
    reader.readAsDataURL(blob)
  }
  async function record() {
    setError('')
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!mounted.current) { stream.getTracks().forEach(track => track.stop()); return }
      const value = new MediaRecorder(stream)
      recorder.current = value
      const chunks = []
      let bytes = 0
      value.ondataavailable = e => { bytes += e.data.size; chunks.push(e.data); if (bytes > 4 * 1024 * 1024 && value.state === 'recording') value.stop() }
      value.onstop = () => { clearTimeout(timer.current); stream.getTracks().forEach(track => track.stop()); if (mounted.current) { setRecording(false); transcribe(new Blob(chunks, { type: value.mimeType })) } }
      value.start(1000); setRecording(true)
      timer.current = setTimeout(() => { if (value.state === 'recording') value.stop() }, 30000)
    } catch { stream?.getTracks().forEach(track => track.stop()); setError('Microphone unavailable. Use text or a local audio file.') }
  }
  async function speak() {
    setAudio(null)
    const output = result?.agent_result?.output || {}
    const text = output.answer || output.summary || output.reason
    if (typeof text !== 'string') { setError('No plain-text explanation available. Read the structured response.'); return }
    const data = await request.run('/voice/synthesize', { method: 'POST', timeout: 130000, body: { text, input_language: language } })
    if (data?.status === 'ok') setAudio(`data:${data.mime_type};base64,${data.audio_base64}`)
  }
  const available = !!user && status.data?.stt === 'configured_unverified'
  return <fieldset><legend>{t('Local voice')}</legend><VoiceAvailability status={status.data} />
    <p>{t('Advisory only. No permission to operate equipment.')}</p>
    <button type="button" disabled={!available || request.loading || !globalThis.navigator?.mediaDevices || !globalThis.MediaRecorder} onClick={recording ? () => recorder.current.stop() : record}>{t(recording ? 'Stop' : 'Record')}</button>
    <label>Local audio (4 MiB maximum)<input type="file" accept="audio/wav,audio/webm,audio/ogg,audio/mpeg,audio/mp4" disabled={!available || request.loading || recording} onChange={e => transcribe(e.target.files?.[0])} /></label>
    <button type="button" disabled={!result || status.data?.tts !== 'configured_unverified' || request.loading} onClick={speak}>{t('Read response')}</button>
    {audio && <audio controls src={audio} />}{error && <p role="alert">{error}</p>}
    <ApiState request={request} />{request.data?.message && <p role="status">{request.data.message}</p>}
  </fieldset>
}

export function BIReport({ data }) {
  const { t } = useLanguage()
  if (!data) return <p>{t('Unavailable')}</p>
  return <><p>{t('Advisory only. No permission to operate equipment.')}</p><p>Latest {data.sampled_runs} stored runs; metadata available for {data.metadata_runs}. Limit: {data.sample_limit}.</p>
    <table><caption>{t('Operational BI')}</caption><thead><tr><th>Stored metric</th><th>Value</th></tr></thead><tbody>{Object.entries(data.metrics || {}).map(([key, value]) => <tr key={key}><th scope="row">{key.replaceAll('_', ' ')}</th><td>{value == null ? t('Unavailable') : typeof value === 'number' ? Math.round(value * 100) / 100 : value}</td></tr>)}</tbody></table>
    <DataView value={{ evidence_sufficiency: data.evidence_sufficiency, execution_paths: data.execution_paths, model_runtimes: data.model_runtimes, recent_audit: data.recent_audit, limitations: data.limitations }} /></>
}

export function AutomationStatus({ data }) {
  const { t } = useLanguage()
  return <section><h3>{t('Automation status')}</h3><DataView value={data ? { status: data.automation, authority: data.automation_authority, workflows: data.automation_kinds } : null} /><p>LangGraph reasons; n8n schedules and delivers summaries. Human approval stays in the workbench.</p></section>
}

export function ProductWorkspace({ user }) {
  const { t } = useLanguage()
  const status = useResource(user ? '/product/status' : null)
  const allowed = ['reviewer', 'admin'].includes(user?.role)
  const bi = useResource(allowed ? '/bi/operational' : null)
  if (!user) return <p>{t('Sign in to access integrations.')}</p>
  return <section className="panel"><h2>{t('Operational BI')}</h2>{allowed ? <><button onClick={bi.refresh}>Refresh</button><ApiState request={bi} /><BIReport data={bi.data} /></> : <p>Reviewer or administrator access is required for operational metrics.</p>}
    <ApiState request={status} /><AutomationStatus data={status.data} /><VoiceAvailability status={status.data} />
    <p>Only interface labels are translated. Input, evidence quotations and technical identifiers remain original; unsupported languages retain text with English UI fallback.</p>
  </section>
}
