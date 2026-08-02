import type { ReactNode } from 'react'

export function Alert({ kind = 'error', children }: { kind?: 'error' | 'ok'; children: ReactNode }) {
  return <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}
