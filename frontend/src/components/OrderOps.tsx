import { useState } from 'react'

import { ApiError } from '../api/client'
import { ordersApi } from '../api/orders'
import type { Order } from '../api/orders'
import { statusLabel } from '../pages/orderStatus'
import { Alert, Button } from './ui'

/**
 * Restaurant-facing order list with the right action per status:
 * Confirmed → Accept/Reject · Accepted → Start preparing · Preparing → Mark ready.
 * Presentational: the parent fetches `orders` and passes `onChanged` to reload.
 */
export function OrderOps({ orders, onChanged }: { orders: Order[]; onChanged: () => void | Promise<void> }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)

  async function run(action: () => Promise<unknown>, orderId: number) {
    setBusy(orderId)
    setError(null)
    try {
      await action()
      await onChanged()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Action failed.')
    } finally {
      setBusy(null)
    }
  }

  if (orders.length === 0) {
    return <div className="empty">No orders yet.</div>
  }

  return (
    <>
      {error && <Alert>{error}</Alert>}
      <div className="order-list">
        {orders.map((o) => (
          <div key={o.id} className="delivery-card">
            <div>
              <div className="menu-item-name">Order #{o.id}</div>
              <div className="muted">
                {o.items.reduce((n, i) => n + i.quantity, 0)} item(s) · ${Number(o.total).toFixed(2)}
              </div>
            </div>
            <span className="badge">{statusLabel(o.status)}</span>
            <div className="delivery-actions">
              {o.status === 'PAYMENT_SUCCESS' && (
                <>
                  <Button loading={busy === o.id} onClick={() => run(() => ordersApi.accept(o.id), o.id)}>
                    Accept
                  </Button>
                  <Button variant="ghost" loading={busy === o.id} onClick={() => run(() => ordersApi.reject(o.id), o.id)}>
                    Reject
                  </Button>
                </>
              )}
              {o.status === 'RESTAURANT_ACCEPTED' && (
                <Button loading={busy === o.id} onClick={() => run(() => ordersApi.setStatus(o.id, 'PREPARING'), o.id)}>
                  Start preparing
                </Button>
              )}
              {o.status === 'PREPARING' && (
                <Button loading={busy === o.id} onClick={() => run(() => ordersApi.setStatus(o.id, 'READY_FOR_PICKUP'), o.id)}>
                  Mark ready
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
