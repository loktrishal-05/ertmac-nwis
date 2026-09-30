// Run after `npm run build`: fails if development fixture code or schema samples reached the production bundle, or if the
// reference-only generated UI video (kept under data/resources-source) was ever copied into the deployable output.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const dir = fileURLToPath(new URL('../dist/assets/', import.meta.url))
const markers = ['fixture-engineer', 'NWIS Demo Field', 'fixtureResponse', 'VITE_NWIS_FIXTURES', 'SCHEMA TEST SAMPLES']
const hits = readdirSync(dir).filter(name => name.endsWith('.js'))
  .flatMap(name => { const text = readFileSync(join(dir, name), 'utf8'); return markers.filter(marker => text.includes(marker)).map(marker => `${name}: ${marker}`) })
if (hits.length) { console.error('Fixture code found in production bundle:\n' + hits.join('\n')); process.exit(1) }
const all = (root, prefix = '') => readdirSync(root, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? all(join(root, entry.name), `${prefix}${entry.name}/`) : [`${prefix}${entry.name}`])
const reference = all(fileURLToPath(new URL('../dist/', import.meta.url))).filter(name => /generated-ui-reference|-original\.(mp4|png)$/i.test(name))
if (reference.length) { console.error(`Reference-only / original source media found in dist:\n${reference.join('\n')}`); process.exit(1) }
console.log('dist: no NWIS fixture or schema-sample code in the production bundle; no reference-only media.')
