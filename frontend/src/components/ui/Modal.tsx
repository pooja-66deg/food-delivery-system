import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

interface ModalProps {
  open: boolean
  title: string
  /** Optional line under the title explaining what the form is for. */
  subtitle?: string
  onClose: () => void
  children: ReactNode
}

/**
 * A dialog for content that interrupts the page — a create form, say — rather
 * than the yes/no question ConfirmDialog handles.
 *
 * Closes on Escape and on a backdrop click, and moves focus into the panel on
 * open so a keyboard user is not left tabbing through the page behind it. The
 * page underneath is locked from scrolling while it is up, because a dialog that
 * scrolls the content behind it reads as broken.
 */
export function Modal({ open, title, subtitle, onClose, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement | null>(null)

  // The latest onClose, without it being a dependency below. Callers almost
  // always pass an inline arrow, which is a new identity on every render — and
  // with onClose in the dependency list this effect re-ran on every keystroke
  // and called panelRef.focus(), pulling focus out of whatever input the user
  // was typing into. A form inside a Modal accepted exactly one character.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', onKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    // Only on open, which is the whole point: moving focus into the panel is a
    // one-time courtesy, not something to redo while someone is typing.
    panelRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  if (!open) return null

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        ref={panelRef}
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        tabIndex={-1}
        // Clicks inside the panel are not "click away to dismiss".
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="modal-title">{title}</h2>
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path
                d="M6 6l12 12M18 6 6 18"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}
