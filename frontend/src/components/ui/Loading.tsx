/**
 * Placeholder while a list or detail view is still fetching. role="status" so
 * screen readers announce the wait instead of hitting silence.
 */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="empty" role="status">
      <span className="spin" aria-hidden /> {label}
    </div>
  )
}
