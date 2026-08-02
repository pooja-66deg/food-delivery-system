import type { ReactNode } from 'react'

/**
 * The "nothing to show here" slot every list falls back to — a missing record,
 * an empty result, a section the current role can't use.
 */
export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}
