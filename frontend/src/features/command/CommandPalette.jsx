import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../../components/ui.jsx'
import { matchCommands } from '../../app/navigation.js'

// Keyboard-first jump list over the pages this role can open. Native <dialog> gives the focus trap and Escape.
export function CommandPalette({ open, onClose, commands }) {
  const dialog = useRef(null)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const results = useMemo(() => matchCommands(commands, query), [commands, query])

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  }, [open])

  function run(command) {
    onClose()
    setQuery('')
    setActive(0)
    command?.run()
  }
  function onKey(event) {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(i => Math.min(results.length - 1, i + 1)) }
    if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(0, i - 1)) }
    if (event.key === 'Enter') { event.preventDefault(); run(results[Math.min(active, results.length - 1)]) }
  }
  const current = Math.min(active, Math.max(0, results.length - 1))

  return <dialog ref={dialog} className="palette" aria-label="Jump to a page or action" onClose={onClose}
    onClick={event => { if (event.target === dialog.current) onClose() }}>
    {open && <>
      <div className="palette-field"><Icon name="search" size={18} />
        <input autoFocus value={query} onChange={event => { setQuery(event.target.value); setActive(0) }} onKeyDown={onKey}
          placeholder="Jump to a page or action…" aria-label="Search pages and actions" role="combobox" aria-expanded="true" aria-autocomplete="list"
          aria-controls="palette-list" aria-activedescendant={results.length ? `palette-${current}` : undefined} />
        <kbd>Esc</kbd></div>
      <ul id="palette-list" role="listbox" aria-label="Results" className="palette-list">
        {results.length ? results.map((command, index) => <li key={command.id} id={`palette-${index}`} role="option" aria-selected={index === current}
          onPointerMove={() => setActive(index)} onClick={() => run(command)}>
          <Icon name={command.icon} size={18} /><span>{command.label}</span><small>{command.group}</small></li>)
          : <li className="palette-empty" role="option" aria-selected="false" aria-disabled="true">No page or action matches “{query}”.</li>}
      </ul>
      <p className="palette-hint"><kbd>↑</kbd> <kbd>↓</kbd> move · <kbd>Enter</kbd> open · <kbd>Esc</kbd> close</p>
    </>}
  </dialog>
}
