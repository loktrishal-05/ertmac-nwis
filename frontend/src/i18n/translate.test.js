import test from 'node:test'
import assert from 'node:assert/strict'
import { translateText } from './translate.js'
import hi from './hi.js'
import ta from './ta.js'

test('exact UI text is translated and surrounding whitespace is kept', () => {
  assert.equal(translateText(hi, 'Dashboard'), 'डैशबोर्ड')
  assert.equal(translateText(ta, '  Sign in '), '  உள்நுழை ')
})

test('numbers and well identifiers are slots, never translated', () => {
  assert.equal(translateText(hi, '18 results'), '18 परिणाम')
  assert.equal(translateText(ta, 'next 150 m'), 'அடுத்த 150 மீ.')
  assert.equal(translateText(hi, 'ACTIVE-01'), 'ACTIVE-01')
  assert.equal(translateText(hi, 'OFF-04: rank 1, score 0.96, 1.5 km, 6 historical events'), 'OFF-04: क्रम 1, स्कोर 0.96, 1.5 कि.मी., 6 ऐतिहासिक घटनाएँ')
})

test('unknown text, data and punctuation pass through unchanged', () => {
  assert.equal(translateText(hi, 'String stuck at 2,529 m MD after connection'), 'String stuck at 2,529 m MD after connection')
  assert.equal(translateText(hi, '2,450 m'), '2,450 मी.')
  assert.equal(translateText(ta, '5 km'), '5 கி.மீ.')
  assert.equal(translateText(hi, '—'), '—')
  assert.equal(translateText(null, 'Dashboard'), 'Dashboard')
})

test('Hindi and Tamil cover exactly the same UI text, with matching number slots', () => {
  assert.deepEqual(Object.keys(ta).sort(), Object.keys(hi).sort())
  const slots = text => (text.match(/\{\}/g) || []).length
  for (const [key, value] of Object.entries(hi)) {
    assert.equal(slots(value), slots(key), `hi slots for ${key}`)
    assert.equal(slots(ta[key]), slots(key), `ta slots for ${key}`)
    assert.ok(value.trim() && ta[key].trim(), `empty translation for ${key}`)
  }
})
