import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { ordersApi } from '../api/orders'
import type { Order, Payment } from '../api/orders'
import { useCart } from '../cart/CartContext'
import { Alert, Button } from '../components/ui'
import { canCustomerCancel, statusLabel } from './orderStatus'

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { refresh: refreshCart } = useCart()
  const [order, setOrder] = useState<Order | null>(null)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    setError(null)
    try {
      const o = await ordersApi.get(Number(id))
      setOrder(o)
      setPayment(await ordersApi.payment(o.id).catch(() => null))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load order.')
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  async function cancel() {
    if (!order) return
    setError(null)
    setCancelling(true)
    try {
      await ordersApi.cancel(order.id)
      await Promise.all([load(), refreshCart()])
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not cancel.')
    } finally {
      setCancelling(false)
    }
  }

  if (error) {
    return (
      <main className="app-main">
        <Link to="/orders" className="back-link">← Back to orders</Link>
        <Alert>{error}</Alert>
      </main>
    )
  }

  if (!order) {
    return (
      <main className="app-main">
        <div className="empty"><span className="spin" aria-hidden /> Loading…</div>
      </main>
    )
  }

  return (
    <main className="app-main">
      <Link to="/orders" className="back-link">← Back to orders</Link>

      <div className="rest-hero">
        <div className="rest-hero-head">
          <h1>Order #{order.id}</h1>
          <span className="badge">{statusLabel(order.status)}</span>
        </div>
        <div className="rest-hero-meta">
          <span className="chip">{order.payment_method}</span>
          <span className="chip">Payment: {payment?.status ?? order.payment_status}</span>
          {order.refund_status !== 'NONE' && <span className="chip">Refund: {order.refund_status}</span>}
        </div>
      </div>

      <section className="menu-section">
        <h2>Items</h2>
        <div className="menu-items">
          {order.items.map((it) => (
            <div key={it.menu_item_id} className="menu-item">
              <div className="menu-item-name">{it.name} × {it.quantity}</div>
              <div className="price">${Number(it.line_total).toFixed(2)}</div>
            </div>
          ))}
        </div>
        <div className="cart-total">
          <span>Total</span>
          <span className="price">${Number(order.total).toFixed(2)}</span>
        </div>
      </section>

      <section className="menu-section">
        <h2>Progress</h2>
        <ol className="timeline">
          {order.events.map((e, i) => (
            <li key={i} className="timeline-item">
              <span className="timeline-dot" aria-hidden />
              <div>
                <div className="menu-item-name">{statusLabel(e.to_status)}</div>
                <div className="muted">
                  {new Date(e.at).toLocaleString()} · {e.actor.toLowerCase()}
                  {e.reason ? ` · ${e.reason}` : ''}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {canCustomerCancel(order.status) && (
        <Button variant="ghost" loading={cancelling} onClick={cancel}>
          Cancel order
        </Button>
      )}
    </main>
  )
}
