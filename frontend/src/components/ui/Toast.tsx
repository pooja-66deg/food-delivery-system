import type { ToastType } from '../../lib/useTimedNotice'

const TOAST_LABELS: Record<ToastType, string> = {
  add: 'Added',
  edit: 'Updated',
  delete: 'Deleted',
}

export function Toast({ type, message }: { type: ToastType; message: string }) {
  return (
    <div className={`toast toast-${type}`} role="status" aria-live="polite">
      <span className="toast-type">{TOAST_LABELS[type]}</span>
      <span className="toast-message">{message}</span>
    </div>
  )
}
