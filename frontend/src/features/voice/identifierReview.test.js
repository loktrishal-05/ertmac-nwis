import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { REVIEW_REASONS, VOICE_FAILURES, isSubstantialReplacement, normalizeAudioMime, reasonInfo, reviewGate,
  reviewSegments, voiceAvailability, voiceFailureMessage } from './identifierReview.js'

const joined = segments => segments.map(segment => segment.text).join('')

test('segments slice by code point and never alter the raw transcript', () => {
  for (const [text, flagged] of [['Check P 204 A vibration', 'P 204 A'], ['पंप P204A का कंपन देखें', 'P204A'],
    ['பம்ப் p204a அதிர்வு', 'p204a'], ['🔧🔧 XV-2040 open?', 'XV-2040']]) {
    const start = Array.from(text.slice(0, text.indexOf(flagged))).length // Code points, as the backend counts.
    const segments = reviewSegments(text, [{ start, end: start + Array.from(flagged).length, text: flagged, reasons: ['malformed_identifier'] }])
    assert.equal(joined(segments), text)
    assert.deepEqual(segments.filter(s => s.flag !== null), [{ text: flagged, flag: 0 }])
  }
})

test('mismatched, out-of-range and overlapping offsets are not highlighted', () => {
  const text = 'pump P 204 A trips'
  assert.ok(reviewSegments(text, [{ start: 0, end: 4, text: 'P 20' }]).every(s => s.flag === null))
  assert.ok(reviewSegments(text, [{ start: 5, end: 99, text: 'x' }, { start: 3, end: 3 }, { start: -1, end: 2 }]).every(s => s.flag === null))
  const overlap = reviewSegments(text, [{ start: 5, end: 12, text: 'P 204 A' }, { start: 7, end: 10, text: '204' }])
  assert.equal(joined(overlap), text)
  assert.deepEqual(overlap.filter(s => s.flag !== null).map(s => s.flag), [0])
  assert.equal(joined(reviewSegments('', [])), '')
})

test('gate requires every flag acknowledged and the transcript confirmed', () => {
  const result = { identifier_review: [{ reasons: ['possible_split_identifier'] }, { reasons: ['brand_new_reason'] }] }
  assert.deepEqual(reviewGate({ result }), { total: 2, pending: [0, 1], ready: false })
  assert.equal(reviewGate({ result, acknowledged: [0, 1] }).ready, false)
  assert.equal(reviewGate({ result, acknowledged: [0], confirmed: true }).ready, false)
  assert.equal(reviewGate({ result, acknowledged: [0, 1], confirmed: true }).ready, true)
  assert.equal(reviewGate({ result: { identifier_review: [] } }).ready, false)
  assert.equal(reviewGate({ result: { identifier_review: [] }, confirmed: true }).ready, true)
  assert.equal(reasonInfo('brand_new_reason').label, 'Needs review')
})

test('all 10 review reasons and 8 failure states are explained', () => {
  const reasons = ['possible_split_identifier', 'malformed_identifier', 'malformed_document_identifier', 'possible_document_prefix',
    'possible_identifier_fragment', 'suspicious_engineering_unit', 'spoken_engineering_measurement', 'non_canonical_case',
    'low_word_confidence', 'low_transcript_confidence']
  assert.deepEqual(Object.keys(REVIEW_REASONS).sort(), [...reasons].sort())
  const failures = ['not_configured', 'runtime_unavailable', 'timeout', 'invalid_response', 'policy_denied',
    'unsupported_audio_format', 'invalid_audio', 'unsupported_language']
  assert.deepEqual(Object.keys(VOICE_FAILURES).sort(), [...failures].sort())
  for (const reason of failures.slice(0, 7)) assert.equal(voiceFailureMessage({ status: 'unavailable', reason }), VOICE_FAILURES[reason])
  assert.equal(voiceFailureMessage({ status: 'unsupported_language' }), VOICE_FAILURES.unsupported_language)
  assert.match(voiceFailureMessage({ status: 'unavailable', reason: 'future' }), /Text mode remains available/)
})

test('substantial replacement, MIME aliases and stt_health availability', () => {
  assert.equal(isSubstantialReplacement('check P 204 A vibration trend', 'check P204A vibration trend'), false)
  assert.equal(isSubstantialReplacement('check P 204 A vibration trend', 'what is the SOP for XV-2040 isolation'), true)
  assert.equal(isSubstantialReplacement('', 'anything'), false)
  assert.equal(normalizeAudioMime('audio/webm;codecs=opus'), 'audio/webm')
  for (const [input, output] of [['audio/x-wav', 'audio/wav'], ['audio/x-m4a', 'audio/mp4'], ['audio/mp3', 'audio/mpeg'], ['video/webm', 'audio/webm']]) assert.equal(normalizeAudioMime(input), output)
  for (const input of ['audio/flac', '', undefined, 'text/plain']) assert.equal(normalizeAudioMime(input), null)
  const user = { role: 'requester' }
  const down = voiceAvailability({ stt: 'configured_unverified', stt_health: 'unavailable' }, user)
  assert.equal(down.canRecord, false)
  assert.equal(down.configuredButDown, true)
  assert.equal(voiceAvailability({ stt_health: 'ready', tts_health: 'ready' }, user).canRecord, true)
  assert.equal(voiceAvailability({ stt_health: 'ready' }, null).canRecord, false)
})

test('review UI shows the exact transcript and the form refuses gated submission, including Enter', async () => {
  const server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, esbuild: { jsx: 'automatic' } })
  try {
    const { TranscriptReview, QueryForm } = await server.ssrLoadModule('/src/features/voice/TranscriptReview.jsx')
    const result = { text: 'Check P 204 A <b>now</b>', identifier_review: [{ start: 6, end: 13, text: 'P 204 A', reasons: ['possible_split_identifier', 'mystery'] }] }
    const html = renderToStaticMarkup(createElement(TranscriptReview, { result }))
    assert.match(html, /<mark class="flagged-span" aria-describedby="flag-0">P 204 A/)
    assert.ok(html.includes('&lt;b&gt;now&lt;/b&gt;') && !html.includes('<b>now'))
    for (const text of ['Possibly split identifier', 'Needs review', '0 of 1 flags reviewed']) assert.ok(html.includes(text))

    let submitted = 0
    const form = (gate, query = 'Check P204A') => QueryForm({ query, onChange: () => {}, onSubmit: () => { submitted += 1 }, gate })
    const event = { preventDefault() {} }
    const locked = form(reviewGate({ result }))
    locked.props.onSubmit(event) // Enter in a field submits through this same handler.
    assert.equal(submitted, 0)
    const lockedHtml = renderToStaticMarkup(locked)
    assert.match(lockedHtml, /Submission is locked/)
    assert.match(lockedHtml, /<button type="submit" disabled=""/)
    const ready = reviewGate({ result, acknowledged: [0], confirmed: true })
    form(ready).props.onSubmit(event)
    assert.equal(submitted, 1)
    form(ready, '   ').props.onSubmit(event)
    assert.equal(submitted, 1)
  } finally { await server.close() }
})
