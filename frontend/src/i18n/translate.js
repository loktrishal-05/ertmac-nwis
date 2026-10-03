// Whole-site UI translation from curated dictionaries, applied to rendered text in place.
// React keeps owning the nodes: when it writes new English text, the observer translates it again.
// Never translated: evidence quotes, identifiers, code, form values and model output (see SKIP).

// Form values are never text nodes, so inputs still get translated placeholders / labels; textarea content is skipped.
export const SKIP = 'script,style,code,pre,blockquote,[translate="no"],[data-no-translate]'
const SKIP_TEXT = `${SKIP},textarea`
const ATTRS = ['placeholder', 'aria-label', 'title', 'alt']
// Numbers, percentages and identifiers such as ACTIVE-01 or OFF-04-DDR are slots: "{} results" matches "18 results".
const SLOT = /\d+(?:[.,]\d+)*%?|\b[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\b/g // "1," in "rank 1, score" keeps its comma

export function translateText(dict, text) {
  if (!dict || !text) return text
  const core = text.trim().replace(/\s+/g, ' ') // "5 km" looks up as "5 km"
  if (!core || !/\p{L}/u.test(core)) return text
  let out = dict[core]
  if (out == null) {
    const values = []
    const template = core.replace(SLOT, match => (values.push(match), '{}'))
    if (values.length && dict[template] != null) {
      let i = 0
      out = dict[template].replace(/\{\}/g, () => values[i++] ?? '')
    }
  }
  return out == null ? text : text.match(/^\s*/)[0] + out + text.match(/\s*$/)[0]
}

const textSource = new WeakMap() // text node -> English source
const textWritten = new WeakMap() // text node -> value we last wrote
const attrState = new WeakMap() // element -> { attr: [source, written] }
let dict = null
let observer = null

const skipped = element => !element || !!element.closest(SKIP)

function applyText(node) {
  if (!node.parentElement || node.parentElement.closest(SKIP_TEXT)) return
  const current = node.nodeValue
  if (textWritten.get(node) !== current) textSource.set(node, current) // React or the app wrote new text
  const next = translateText(dict, textSource.get(node))
  if (next !== current) node.nodeValue = next
  textWritten.set(node, next)
}

function applyAttrs(element) {
  if (skipped(element)) return
  const state = attrState.get(element) || {}
  for (const name of ATTRS) {
    const current = element.getAttribute(name)
    if (current == null) continue
    if (state[name]?.[1] !== current) state[name] = [current, current]
    const next = translateText(dict, state[name][0])
    if (next !== current) element.setAttribute(name, next)
    state[name][1] = next
  }
  attrState.set(element, state)
}

function apply(node) {
  if (node.nodeType === Node.TEXT_NODE) return applyText(node)
  if (node.nodeType !== Node.ELEMENT_NODE || skipped(node)) return
  applyAttrs(node)
  for (const child of node.childNodes) apply(child)
}

const loaders = { hi: () => import('./hi.js'), ta: () => import('./ta.js') }

// Switch the whole document to `language` ('en' restores the English source text).
export async function setDocumentLanguage(language) {
  dict = loaders[language] ? (await loaders[language]()).default : null
  if (typeof document === 'undefined') return
  apply(document.documentElement)
  if (!observer) {
    observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') apply(record.target)
        else if (record.type === 'attributes') applyAttrs(record.target)
        else record.addedNodes.forEach(apply)
      }
    })
    observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS })
  }
}
