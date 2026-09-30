// H3: human review of voice transcripts. Pure logic only; the transcript is never rewritten here.

// Every reason the backend currently emits (backend/app/services/local_voice.py).
export const REVIEW_REASONS = {
  possible_split_identifier: {
    label: 'Possibly split identifier',
    help: 'Speech recognition may have inserted spaces into a tag, for example "P 204 A". Check the exact identifier.',
  },
  malformed_identifier: {
    label: 'Malformed identifier',
    help: 'Looks like an equipment or instrument tag but does not match the expected format, for example "P204A".',
  },
  malformed_document_identifier: {
    label: 'Malformed document identifier',
    help: 'Looks like an SOP, work-order or document ID but its separators or format are wrong.',
  },
  possible_document_prefix: {
    label: 'Possible document prefix error',
    help: 'The prefix differs by one letter from a known document prefix, for example "SOC" instead of "SOP".',
  },
  possible_identifier_fragment: {
    label: 'Possible identifier fragment',
    help: 'A number-and-letter fragment such as "204D" may be part of a tag whose prefix was misheard.',
  },
  suspicious_engineering_unit: {
    label: 'Suspicious engineering unit',
    help: 'A value and unit are written unusually, for example "7.1mm-S". Confirm the value and the unit.',
  },
  spoken_engineering_measurement: {
    label: 'Measurement written in words',
    help: 'A measurement was transcribed as words, for example "seven point one millimetres per second". Confirm it.',
  },
  non_canonical_case: {
    label: 'Unusual capitalisation',
    help: 'Identifier letters are not in the expected upper case. Tags are case-sensitive in some systems.',
  },
  low_word_confidence: {
    label: 'Low recognition confidence',
    help: 'The local speech engine was not confident about these words.',
  },
  low_transcript_confidence: {
    label: 'Low transcript confidence',
    help: 'The whole transcript has low confidence. Check every identifier and value.',
  },
}

// Unknown reasons still require review: fail safe rather than silently accept.
export function reasonInfo(reason) {
  return REVIEW_REASONS[reason] || { label: 'Needs review', help: `Unrecognised review reason "${reason}". Check this text carefully.` }
}

export const VOICE_FAILURES = {
  not_configured: 'Local speech-to-text is not configured on this Workbench. Type your question instead.',
  runtime_unavailable: 'The local speech service is not responding. Type your question, or try again later.',
  timeout: 'Transcription timed out. Try a shorter recording, or type your question.',
  invalid_response: 'The local speech service returned an unusable response. Type your question instead.',
  policy_denied: 'Speech processing was blocked by the data policy: only approved local speech resources may process confidential audio.',
  unsupported_audio_format: 'This audio format is not supported. Record again, or upload WAV, WebM, Ogg, MP3 or MP4 audio.',
  invalid_audio: 'The audio could not be used. It may be empty, damaged or longer than 60 seconds.',
  unsupported_language: 'Speech is not available for this language. Text mode remains available.',
}

export function voiceFailureMessage(result) {
  const key = result?.status === 'unsupported_language' ? 'unsupported_language' : result?.reason
  return VOICE_FAILURES[key] || 'Voice input is unavailable. Text mode remains available.'
}

// Backend offsets count Unicode code points (Python); JavaScript strings index UTF-16 units.
// Slice through Array.from so Devanagari, Tamil and emoji never shift a highlight.
export function reviewSegments(text, flags = []) {
  const chars = Array.from(text || '')
  const ranges = flags
    .map((flag, index) => ({ index, start: flag.start, end: flag.end, text: flag.text }))
    .filter(r => Number.isInteger(r.start) && Number.isInteger(r.end) && r.start >= 0 && r.start < r.end && r.end <= chars.length)
    // Highlight only where the offsets demonstrably point at the flagged text.
    .filter(r => r.text === undefined || chars.slice(r.start, r.end).join('') === r.text)
    .sort((a, b) => a.start - b.start || b.end - a.end)
  const segments = []
  let cursor = 0
  for (const range of ranges) {
    if (range.start < cursor) continue // Overlapping flags stay listed and acknowledged separately.
    if (range.start > cursor) segments.push({ text: chars.slice(cursor, range.start).join(''), flag: null })
    segments.push({ text: chars.slice(range.start, range.end).join(''), flag: range.index })
    cursor = range.end
  }
  if (cursor < chars.length) segments.push({ text: chars.slice(cursor).join(''), flag: null })
  return segments
}

// Submission requires every flag acknowledged AND the whole transcript confirmed.
export function reviewGate({ result, acknowledged = [], confirmed = false }) {
  const flags = result?.identifier_review || []
  const pending = flags.map((_, index) => index).filter(index => !acknowledged.includes(index))
  return { total: flags.length, pending, ready: pending.length === 0 && confirmed === true }
}

const words = value => (value || '').toLocaleLowerCase().split(/\s+/).filter(Boolean)

// Correcting identifiers keeps most words; replacing the question does not.
export function isSubstantialReplacement(original, current, threshold = 0.5) {
  const before = words(original)
  if (!before.length) return false
  const remaining = new Map()
  for (const word of words(current)) remaining.set(word, (remaining.get(word) || 0) + 1)
  let kept = 0
  for (const word of before) {
    if (remaining.get(word)) { kept += 1; remaining.set(word, remaining.get(word) - 1) }
  }
  return kept / before.length < threshold
}

const MIME_ALIASES = {
  'audio/x-wav': 'audio/wav', 'audio/wave': 'audio/wav', 'audio/vnd.wave': 'audio/wav',
  'audio/x-m4a': 'audio/mp4', 'audio/m4a': 'audio/mp4', 'audio/aac': 'audio/mp4',
  'audio/mp3': 'audio/mpeg', 'video/webm': 'audio/webm', 'video/mp4': 'audio/mp4',
}
const SUPPORTED_MIME = new Set(['audio/wav', 'audio/webm', 'audio/ogg', 'audio/mpeg', 'audio/mp4'])

// Browser MIME strings carry codecs ("audio/webm;codecs=opus") and vendor aliases.
export function normalizeAudioMime(type) {
  const base = (type || '').split(';')[0].trim().toLowerCase()
  const mime = MIME_ALIASES[base] || base
  return SUPPORTED_MIME.has(mime) ? mime : null
}

// Record/upload only when the live local health probe says ready, not merely "configured".
export function voiceAvailability(status, user) {
  const signedIn = !!user
  return {
    canRecord: signedIn && status?.stt_health === 'ready',
    canSpeak: signedIn && status?.tts_health === 'ready',
    configuredButDown: status?.stt === 'configured_unverified' && status?.stt_health !== 'ready',
  }
}
