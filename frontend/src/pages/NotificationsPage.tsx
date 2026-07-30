import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { notificationsApi } from '../api/notifications'
import type { Notification } from '../api/notifications'
import { useAuth } from '../auth/AuthContext'
import { useNotifications } from '../notifications/NotificationsContext'
import { Alert } from '../components/ui'

export function NotificationsPage() {
  const { user } = useAuth()
  const { markAllSeen } = useNotifications()
  const navigate = useNavigate()
  const [items, setItems] = useState<Notification[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    notificationsApi
      .list()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load notifications.'))
    // Opening the inbox clears the unread badge.
    markAllSeen()
  }, [markAllSeen])

  // Where a notification links, based on the viewer's role.
  function targetFor(n: Notification): string | null {
    if (n.order_id == null) return null
    if (user?.role === 'customer') return `/orders/${n.order_id}`
    if (user?.role === 'restaurant' || user?.role === 'admin') return '/restaurant/orders'
    if (user?.role === 'driver') return '/deliveries'
    return null
  }

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
          {items.map((n) => {
            const to = targetFor(n)
            return (
              <div
                key={n.id}
                className="notif-row"
                data-clickable={to !== null}
                role={to ? 'button' : undefined}
                tabIndex={to ? 0 : undefined}
                onClick={to ? () => navigate(to) : undefined}
                onKeyDown={to ? (e) => (e.key === 'Enter' || e.key === ' ') && navigate(to) : undefined}
              >
                <span className="notif-dot" aria-hidden />
                <div className="notif-body">
                  <div>{n.message}</div>
                  <div className="muted">
                    {new Date(n.created_at).toLocaleString()}
                    {n.order_id ? ` · order #${n.order_id}` : ''}
                    {to ? ' · view →' : ''}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </main>
  )
}
