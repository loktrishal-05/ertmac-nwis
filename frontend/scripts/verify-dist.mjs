// Run after `npm run build`: fails if development fixture code or schema samples reached the production bundle.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const dir = fileURLToPath(new URL('../dist/assets/', import.meta.url))
const markers = ['fixture-engineer', 'NWIS Demo Field', 'fixtureResponse', 'VITE_NWIS_FIXTURES', 'SCHEMA TEST SAMPLES']
const hits = readdirSync(dir).filter(name => name.endsWith('.js'))
  .flatMap(name => { const text = readFileSync(join(dir, name), 'utf8'); return markers.filter(marker => text.includes(marker)).map(marker => `${name}: ${marker}`) })
if (hits.length) { console.error('Fixture code found in production bundle:\n' + hits.join('\n')); process.exit(1) }
console.log('dist: no NWIS fixture or schema-sample code in the production bundle.')
