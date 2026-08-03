import type { ChangeEvent } from 'react'

/**
 * Styled file input for image uploads. Keeps the label/input pairing (and the
 * accept filter) in one place instead of repeating it per upload site.
 */
interface FilePickerProps {
  label: string
  onPick: (file: File) => void
  /** Compact variant for the inline controls on a menu row. */
  small?: boolean
}

export function FilePicker({ label, onPick, small = false }: FilePickerProps) {
  const handle = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onPick(file)
    // Clear the value so picking the same file twice still fires a change.
    e.target.value = ''
  }

  return (
    <label className={`file-label${small ? ' file-label-sm' : ''}`}>
      {label}
      <input type="file" accept="image/*" onChange={handle} />
    </label>
  )
}
