import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { ordersApi } from '../../api/orders'
import type { Order } from '../../api/orders'
import { Alert, Button } from '../../components/ui'
import { statusLabel } from '../orderStatus'
import { timeAgo } from './ownerStats'

interface OrderTicketProps {
  order: Order
  /** Which kitchen it is for — the dashboard mixes every restaurant's orders. */
  restaurantName: string
  now: Date
  onChanged: () => void | Promise<void>
}

/**
 * One order as a kitchen ticket: who it is for, what is on it, and the single
 * next thing to do with it.
 *
 * The action set is deliberately the *next* step only. A row of every possible
 * transition invites an owner to mark an order ready before it is cooked.
 */
export function OrderTicket({ order, restaurantName, now, onChanged }: OrderTicketProps) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      await onChanged()
    } catch (e) {
      setError(errorMessage(e, 'Action failed.'))
    } finally {
      setBusy(false)
    }
  }

  const itemTotal = order.items.reduce((n, i) => n + i.quantity, 0)

  return (
    <article className="ticket">
      <div className="ticket-head">
        <div>
          <h3 className="ticket-title">
            #{order.id} · {restaurantName}
          </h3>
          <p className="muted ticket-meta">
            {timeAgo(order.created_at, now)} · {order.payment_method === 'COD' ? 'Cash' : 'Card'} ·{' '}
            {itemTotal === 1 ? '1 item' : `${itemTotal} items`}
          </p>
        </div>
        <span className={`ticket-status status-${order.status.toLowerCase()}`}>
          {statusLabel(order.status)}
        </span>
      </div>

      <ul className="ticket-lines">
        {order.items.map((item, i) => (
          <li key={i}>
            <span className="ticket-line-name">
              {item.quantity} × {item.name}
            </span>
            <span className="ticket-line-price">${Number(item.line_total).toFixed(2)}</span>
          </li>
        ))}
      </ul>

      {error && <Alert>{error}</Alert>}

      <div className="ticket-foot">
        <span className="ticket-total">${Number(order.total).toFixed(2)}</span>
        <div className="ticket-actions">
          {order.status === 'PAYMENT_SUCCESS' && (
            <>
              <Button variant="ghost" loading={busy} onClick={() => run(() => ordersApi.reject(order.id))}>
                Reject
              </Button>
              <Button loading={busy} onClick={() => run(() => ordersApi.accept(order.id))}>
                Accept
              </Button>
            </>
          )}
          {order.status === 'RESTAURANT_ACCEPTED' && (
            <Button loading={busy} onClick={() => run(() => ordersApi.setStatus(order.id, 'PREPARING'))}>
              Start
            </Button>
          )}
          {order.status === 'PREPARING' && (
            <Button
              loading={busy}
              onClick={() => run(() => ordersApi.setStatus(order.id, 'READY_FOR_PICKUP'))}
            >
              Mark ready
            </Button>
          )}
        </div>
      </div>
    </article>
  )
}
