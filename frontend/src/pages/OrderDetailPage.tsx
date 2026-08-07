import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { ApiError, errorMessage } from '../api/client'
import { deliveryApi } from '../api/delivery'
import type { Tracking } from '../api/delivery'
import { ordersApi } from '../api/orders'
import type { Order, Payment } from '../api/orders'
import { paymentsApi } from '../api/payments'
import { reviewsApi } from '../api/reviews'
import { useAuth } from '../auth/AuthContext'
import { useCart } from '../cart/CartContext'
import { DeliveryMap } from '../components/DeliveryMap'
import { Alert, Button, Loading } from '../components/ui'
import { canCustomerCancel, statusLabel } from './orderStatus'

const REVIEWABLE = new Set(['DELIVERED', 'COMPLETED'])

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  // Stripe's success_url carries this back. It is only a hint that a payment
  // may have gone through — the server checks with Stripe before believing it.
  const returnedFromCheckout = searchParams.get('paid') === '1'
  const [confirming, setConfirming] = useState(returnedFromCheckout)
  const { user } = useAuth()
  const { refresh: refreshCart } = useCart()
  const [order, setOrder] = useState<Order | null>(null)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [tracking, setTracking] = useState<Tracking | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [retrying, setRetrying] = useState(false)

  // review form
  const [rating, setRating] = useState(5)
  const [comment, setComment] = useState('')
  const [reviewing, setReviewing] = useState(false)
  const [reviewed, setReviewed] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    setError(null)
    try {
      const o = await ordersApi.get(Number(id))
      setOrder(o)
      setPayment(await paymentsApi.forOrder(o.id).catch(() => null))
    } catch (e) {
      setError(errorMessage(e, 'Failed to load order.'))
    }
  }, [id])

  // Settle first, then load — otherwise the page paints the pre-payment status
  // and only corrects itself on the next refresh.
  useEffect(() => {
    if (!confirming || !id) return
    let active = true
    paymentsApi
      .confirm(Number(id))
      // A failure here is not the customer's problem: the webhook may have
      // already settled it, and the load below reports whatever is true.
      .catch(() => {})
      .finally(() => {
        if (!active) return
        // Drop the marker so a reload does not look like a fresh return.
        searchParams.delete('paid')
        setSearchParams(searchParams, { replace: true })
        setConfirming(false)
      })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirming, id])

  useEffect(() => {
    if (confirming) return
    void load()
  }, [load, confirming])

  // Poll live tracking while the order is out for delivery.
  useEffect(() => {
    if (!order || order.status !== 'OUT_FOR_DELIVERY') {
      setTracking(null)
      return
    }
    let active = true
    const tick = () => deliveryApi.tracking(order.id).then((t) => active && setTracking(t)).catch(() => {})
    void tick()
    const timer = setInterval(tick, 5000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [order])

  async function cancel() {
    if (!order) return
    setError(null)
    setCancelling(true)
    try {
      await ordersApi.cancel(order.id)
      await Promise.all([load(), refreshCart()])
    } catch (e) {
      setError(errorMessage(e, 'Could not cancel.'))
    } finally {
      setCancelling(false)
    }
  }

  async function retryPayment() {
    if (!order) return
    setRetrying(true)
    setError(null)
    try {
      await paymentsApi.retry(order.id)
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Retry failed.'))
    } finally {
      setRetrying(false)
    }
  }

  async function submitReview() {
    if (!order) return
    setReviewing(true)
    setError(null)
    try {
      await reviewsApi.create(order.id, rating, comment || undefined)
      setReviewed(true)
      setNotice('Thanks for your review!')
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setReviewed(true)
        setNotice('You have already reviewed this order.')
      } else {
        setError(errorMessage(e, 'Could not submit review.'))
      }
    } finally {
      setReviewing(false)
    }
  }

  if (error && !order) {
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
        <Loading label={confirming ? 'Confirming your payment…' : undefined} />
      </main>
    )
  }

  const isCustomer = user?.role === 'customer'

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

      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="ok">{notice}</Alert>}

      {payment?.status === 'FAILED' && (
        <Alert>
          Payment failed.{' '}
          <button className="link-inline" onClick={retryPayment} disabled={retrying}>
            {retrying ? 'Retrying…' : 'Retry payment'}
          </button>
        </Alert>
      )}

      {tracking && <DeliveryMap tracking={tracking} />}

      <section className="menu-section">
        <h2>Items</h2>
        <div className="menu-items">
          {order.items.map((it) => (
            <div key={it.menu_item_id} className="menu-item">
              <div className="menu-item-name">{it.name} × {it.quantity}</div>
              <div className="price">₹{Number(it.line_total).toFixed(2)}</div>
            </div>
          ))}
        </div>
        <div className="cart-total">
          <span>Total</span>
          <span className="price">₹{Number(order.total).toFixed(2)}</span>
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

      {isCustomer && REVIEWABLE.has(order.status) && !reviewed && (
        <section className="menu-section">
          <h2>Rate your order</h2>
          <div className="rating-row" role="radiogroup" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                className="star"
                data-on={n <= rating}
                aria-label={`${n} star${n > 1 ? 's' : ''}`}
                aria-checked={n === rating}
                role="radio"
                onClick={() => setRating(n)}
              >
                ★
              </button>
            ))}
          </div>
          <textarea
            className="input"
            rows={3}
            placeholder="Tell others about your experience (optional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button loading={reviewing} onClick={submitReview}>Submit review</Button>
        </section>
      )}

      {canCustomerCancel(order.status) && (
        <Button variant="ghost" loading={cancelling} onClick={cancel}>
          Cancel order
        </Button>
      )}
    </main>
  )
}
