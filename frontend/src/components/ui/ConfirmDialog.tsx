import { Button } from './Button'

interface ConfirmDialogProps {
  open: boolean
  title: string
  confirmLabel?: string
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  confirmLabel = 'Delete',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  return (
    <div className="confirm-backdrop" onClick={onCancel} role="presentation">
      <div
        className="confirm-dialog card"
        role="alertdialog"
        aria-labelledby="confirm-dialog-title"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <p id="confirm-dialog-title" className="confirm-title">{title}</p>
        <div className="confirm-actions">
          <Button variant="ghost" type="button" onClick={onCancel}>Cancel</Button>
          <Button loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  )
}
