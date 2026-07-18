import type { CSSProperties } from 'react'
import { X } from 'lucide-react'
import type { ClueEntry } from './generator'
import { useDialogFocus } from './useDialogFocus'

export function ClueZoom({ entry, onClose }: { entry: ClueEntry; onClose: () => void }) {
  const dialogRef = useDialogFocus<HTMLElement>(onClose)

  const direction = entry.direction === 'across' ? 'Horizontal' : 'Vertical'
  const arrow = entry.direction === 'across' ? '→' : '↓'
  const preferredWidth = entry.image ? 224 : Math.min(248, Math.max(176, 112 + entry.text.length * 4.3))

  return <div className="clue-zoom-backdrop" role="presentation" onPointerDown={event => {
    if (event.target === event.currentTarget) onClose()
  }}>
    <section ref={dialogRef} tabIndex={-1} className={`clue-popover ${entry.image ? 'clue-popover--image' : ''}`} style={{ '--clue-card-width': `${Math.round(preferredWidth)}px` } as CSSProperties} role="dialog" aria-modal="true" aria-label={`Définition ${direction.toLowerCase()}`}>
      <button data-dialog-autofocus className="clue-popover-close" type="button" aria-label="Fermer la définition" onClick={onClose}><X /></button>
      <span className="clue-popover-direction">{direction}<b aria-hidden="true">{arrow}</b></span>
      {entry.image
        ? <div className="clue-popover-image"><img src={entry.image.asset} alt={entry.image.alt} /></div>
        : <strong>{entry.text}</strong>}
    </section>
  </div>
}
