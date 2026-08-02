import { useCallback, useEffect, useState } from 'react'

export type ToastType = 'add' | 'edit' | 'delete'

export const TOAST_MESSAGES: Record<ToastType, string> = {
  add: 'Menu item added successfully.',
  edit: 'Menu item updated successfully.',
  delete: 'Menu item deleted successfully.',
}

export interface ToastState {
  type: ToastType
  message: string
}

/** Toast that clears itself after `durationMs` (default 4s). */
export function useTimedNotice(durationMs = 4000) {
  const [toast, setToast] = useState<ToastState | null>(null)

  const showToast = useCallback((type: ToastType) => {
    setToast({ type, message: TOAST_MESSAGES[type] })
  }, [])

  const clearToast = useCallback(() => {
    setToast(null)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), durationMs)
    return () => clearTimeout(timer)
  }, [toast, durationMs])

  return { toast, showToast, clearToast }
}
