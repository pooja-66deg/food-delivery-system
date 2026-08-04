import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { cartApi } from '../api/cart'
import { errorMessage } from '../api/client'
import { ordersApi } from '../api/orders'
import type { OrderScope, OrderSummary } from '../api/orders'
import { Alert, Button, EmptyState, Loading } from '../components/ui'
import { CardPaymentStep } from '../payments/CardPaymentStep'
import { StripeElements } from '../payments/StripeElements'
import { statusLabel } from './orderStatus'

const TABS: { scope: Exclude<OrderScope, 'all'>; label: string; empty: string }[] = [
  { scope: 'active', label: 'Active', empty: 'Nothing on the way right now.' },
  { scope: 'past', label: 'Past', empty: 'No completed orders yet.' },
]

export function OrdersPage() {
  const navigate = useNavigate()
  const [scope, setScope] = useState<Exclude<OrderScope, 'all'>>('active')
  const [orders, setOrders] = useState<OrderSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The order whose card step is open, with a freshly minted secret.
  const [paying, setPaying] = useState<{ orderId: number; clientSecret: string } | null>(null)
  // Lines a reorder could not carry over, shown before the customer reaches the
  // cart so a short refill is never a surprise at checkout.
  const [reorderNotice, setReorderNotice] = useState<string[] | null>(null)
  const [reordering, setReordering] = useState<number | null>(null)

  const load = useCallback(async (which: Exclude<OrderScope, 'all'>) => {
    setOrders(null)
    setError(null)
    try {
      setOrders(await ordersApi.list(which))
    } catch (e) {
      setError(errorMessage(e, 'Failed to load orders.'))
      setOrders([])
    }
  }, [])

  useEffect(() => {
    void load(scope)
  }, [load, scope])

  async function startPayment(orderId: number) {
    setError(null)
    try {
      // The checkout secret is never stored, so ask for a fresh one.
      const payment = await ordersApi.resumePayment(orderId)
      if (!payment.client_secret) {
        setError('This order can no longer be paid for online.')
        return
      }
      setPaying({ orderId, clientSecret: payment.client_secret })
    } catch (e) {
      setError(errorMessage(e, 'Could not reopen payment.'))
    }
  }

  if (paying) {
    return (
      <main className="app-main">
        <h1>Pay for order #{paying.orderId}</h1>
        <div className="cart-summary">
          <StripeElements clientSecret={paying.clientSecret}>
            <CardPaymentStep
              onPaid={() => navigate(`/orders/${paying.orderId}`)}
              onCancel={() => setPaying(null)}
            />
          </StripeElements>
        </div>
      </main>
    )
  }

  async function reorder(orderId: number) {
    setError(null)
    setReorderNotice(null)
    setReordering(orderId)
    try {
      const result = await cartApi.reorder(orderId)
      if (result.skipped.length > 0) {
        // Stay put and say what is missing; going straight to the cart would
        // hide the fact that the order came back incomplete.
        setReorderNotice(result.skipped)
      } else {
        navigate('/cart')
      }
    } catch (e) {
      setError(errorMessage(e, 'Could not reorder that.'))
    } finally {
      setReordering(null)
    }
  }

  const active = TABS.find((t) => t.scope === scope)

  return (
    <main className="app-main">
      <h1>Your orders</h1>

      <div className="tabs" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.scope}
            type="button"
            role="tab"
            className="tab"
            aria-selected={scope === tab.scope}
            data-active={scope === tab.scope}
            onClick={() => setScope(tab.scope)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <Alert>{error}</Alert>}

      {reorderNotice && (
        <Alert kind="ok">
          Added what is still available. Not carried over: {reorderNotice.join('; ')}.{' '}
          <Link to="/cart" className="back-link">Go to cart →</Link>
        </Alert>
      )}

      {orders === null ? (
        <Loading />
      ) : orders.length === 0 ? (
        <EmptyState>
          {active?.empty}{' '}
          <Link to="/restaurants" className="back-link">Order something →</Link>
        </EmptyState>
      ) : (
        <div className="order-list">
          {orders.map((o) => (
            <div key={o.id} className="order-row">
              <Link to={`/orders/${o.id}`} className="order-card">
                <div>
                  <div className="menu-item-name">Order #{o.id}</div>
                  <div className="muted">{new Date(o.created_at).toLocaleString()}</div>
                </div>
                <span className="badge">{statusLabel(o.status)}</span>
                <div className="price">${Number(o.total).toFixed(2)}</div>
              </Link>
              {o.status === 'PAYMENT_PENDING' && (
                <Button variant="ghost" onClick={() => void startPayment(o.id)}>
                  Pay now
                </Button>
              )}
              {scope === 'past' && (
                <Button
                  variant="ghost"
                  loading={reordering === o.id}
                  onClick={() => void reorder(o.id)}
                >
                  Reorder
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
