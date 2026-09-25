import { useState } from 'react'
import { useRequest, useResource } from './hooks/useApi.js'
import { ApiState, DataView, Result } from './WorkspacePages.jsx'

export function OperationalWorkspace({ user }) {
  const [view, setView] = useState('Shift Handover')
  const [equipment, setEquipment] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [text, setText] = useState('')
  const [reading, setReading] = useState('')
  const [rules, setRules] = useState('')
  const request = useRequest()
  const notes = useRequest()
  const gaps = useResource(user && view === 'Knowledge Gaps' ? '/knowledge-gaps' : null)
  async function submit(event) {
    event.preventDefault()
    if (view === 'Shift Handover') await request.run('/shift-handover', { method: 'POST', timeout: 180000,
      body: { equipment_tag: equipment, start: new Date(start).toISOString(), end: new Date(end).toISOString() } })
    if (view === 'Environmental Compliance') await request.run('/environmental-compliance', { method: 'POST', timeout: 180000,
      body: { reading_id: reading, rule_ids: rules.split(',').map(x => x.trim()).filter(Boolean) } })
    if (view === 'Operator Notes') await notes.run('/operator-notes', { method: 'POST', body: { equipment_tag: equipment, text } })
  }
  return <section className="panel"><h2>Operational intelligence</h2>
    <p>Advisory only. Observed measurements, human-reported information, synthesis and missing evidence are kept distinct. Human review never authorizes equipment operation.</p>
    {!user ? <p>Sign in to use operational intelligence.</p> : <>
      <nav aria-label="Operational capabilities">{['Shift Handover', 'Environmental Compliance', 'Operator Notes', 'Knowledge Gaps'].map(label => <button key={label} aria-pressed={view === label} onClick={() => { request.reset(); notes.reset(); setView(label) }}>{label}</button>)}</nav>
      <h3>{view}</h3>
      {view !== 'Knowledge Gaps' && <form onSubmit={submit}>
        {view !== 'Environmental Compliance' && <label>Registered equipment tag<input required maxLength={100} value={equipment} onChange={e => setEquipment(e.target.value)} /></label>}
        {view === 'Shift Handover' && <><p>Choose an explicit period of up to 72 hours. Times use your browser timezone; historical records are not current plant conditions.</p><label>Shift start<input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)} /></label><label>Shift end<input type="datetime-local" required value={end} onChange={e => setEnd(e.target.value)} /></label></>}
        {view === 'Environmental Compliance' && <><p>Uses a stored sensor-reading ID and human-reviewed local rule IDs. Missing limits yield INDETERMINATE; this is not legal certification.</p><label>Reading UUID<input required value={reading} onChange={e => setReading(e.target.value)} /></label><label>Verified local rule UUIDs (comma-separated, optional)<input value={rules} onChange={e => setRules(e.target.value)} /></label></>}
        {view === 'Operator Notes' && <><p>Notes are HUMAN-REPORTED, not verified technical truth. Review uses the existing Approvals page; it does not certify plant state.</p><label>Operational note<textarea required maxLength={4000} rows={4} value={text} onChange={e => setText(e.target.value)} /></label></>}
        <button disabled={request.loading || notes.loading}>Submit for advisory review</button>
      </form>}
      {view === 'Operator Notes' ? <><button disabled={!equipment || notes.loading} onClick={() => notes.run(`/operator-notes?equipment_tag=${encodeURIComponent(equipment)}`)}>Load equipment notes</button><ApiState request={notes} /><DataView value={notes.data} /></> : view === 'Knowledge Gaps' ? <><p>Observed evidence gaps from stored runs. This list does not certify resolution or close incidents.</p><button onClick={gaps.refresh}>Refresh gaps</button><ApiState request={gaps} /><DataView value={gaps.data} /></> : <><ApiState request={request} /><Result data={request.data} /></>}
    </>}
  </section>
}
