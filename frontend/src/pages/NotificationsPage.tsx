import { useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { notificationsApi } from '../api/notifications'
import type { Notification } from '../api/notifications'
import { Alert } from '../components/ui'

export function NotificationsPage() {
  const [items, setItems] = useState<Notification[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    notificationsApi
      .list()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load notifications.'))
  }, [])

  return (
    <main className="app-main">
      <h1>Notifications</h1>
      {error && <Alert>{error}</Alert>}
      {!items ? (
        <div className="empty"><span className="spin" aria-hidden /> Loading…</div>
      ) : items.length === 0 ? (
        <div className="empty">Nothing here yet. Order updates will show up here.</div>
      ) : (
        <div className="notif-list">
          {items.map((n) => (
            <div key={n.id} className="notif-row">
              <span className="notif-dot" aria-hidden />
              <div className="notif-body">
                <div>{n.message}</div>
                <div className="muted">
                  {new Date(n.created_at).toLocaleString()}
                  {n.order_id ? ` · order #${n.order_id}` : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
