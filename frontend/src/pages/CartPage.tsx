import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { authApi } from '../api/auth'
import type { Address } from '../api/auth'
import { errorMessage } from '../api/client'
import { ordersApi } from '../api/orders'
import type { PaymentMethod } from '../api/orders'
import { useCart } from '../cart/CartContext'
import { Alert, Button, EmptyState } from '../components/ui'
import { CardPaymentStep } from '../payments/CardPaymentStep'
import { StripeElements } from '../payments/StripeElements'
import { publishableKey } from '../payments/publishableKey'

export function CartPage() {
  const { cart, refresh, update, remove } = useCart()
  const navigate = useNavigate()
  const [addresses, setAddresses] = useState<Address[]>([])
  const [addressId, setAddressId] = useState<number | null>(null)
  const [payMethod, setPayMethod] = useState<PaymentMethod>('COD')
  const [error, setError] = useState<string | null>(null)
  const [placing, setPlacing] = useState(false)
  // Set when checkout hands back a PaymentIntent that still needs confirming.
  const [pending, setPending] = useState<{ orderId: number; clientSecret: string } | null>(null)

  const cardAvailable = publishableKey() !== null

  useEffect(() => {
    void refresh()
    authApi
      .listAddresses()
      .then((rows) => {
        setAddresses(rows)
        const preferred = rows.find((a) => a.is_default) ?? rows[0]
        if (preferred) setAddressId(preferred.id)
      })
      .catch(() => setAddresses([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function checkout() {
    if (!cart || addressId === null) return
    setError(null)
    setPlacing(true)
    try {
      const order = await ordersApi.checkout(addressId, cart.price_hash, payMethod)
      await refresh()
      if (order.payment_client_secret) {
        // The order exists but is not paid for yet — collect the card first.
        setPending({ orderId: order.id, clientSecret: order.payment_client_secret })
        return
      }
      navigate(`/orders/${order.id}`)
    } catch (e) {
      setError(errorMessage(e, 'Checkout failed.'))
    } finally {
      setPlacing(false)
    }
  }

  const empty = !cart || cart.items.length === 0

  if (pending) {
    return (
      <main className="app-main">
        <h1>Pay for order #{pending.orderId}</h1>
        <p className="muted">
          Your order is held while you pay. You can also finish this later from your orders.
        </p>
        <div className="cart-summary">
          <StripeElements clientSecret={pending.clientSecret}>
            <CardPaymentStep
              onPaid={() => navigate(`/orders/${pending.orderId}`)}
              onCancel={() => navigate(`/orders/${pending.orderId}`)}
            />
          </StripeElements>
        </div>
      </main>
    )
  }

  return (
    <main className="app-main">
      <h1>Your cart</h1>

      {error && <Alert>{error}</Alert>}

      {empty ? (
        <EmptyState>
          Your cart is empty. <Link to="/restaurants" className="back-link">Browse restaurants →</Link>
        </EmptyState>
      ) : (
        <>
          <div className="cart-list">
            {cart.items.map((item) => (
              <div key={item.menu_item_id} className="cart-row">
                <div>
                  <div className="menu-item-name">{item.name}</div>
                  <div className="muted">${Number(item.unit_price).toFixed(2)} each</div>
                </div>
                <div className="cart-qty">
                  <button
                    className="qty-btn"
                    aria-label="Decrease quantity"
                    onClick={() => update(item.menu_item_id, item.quantity - 1)}
                  >
                    −
                  </button>
                  <span>{item.quantity}</span>
                  <button
                    className="qty-btn"
                    aria-label="Increase quantity"
                    onClick={() => update(item.menu_item_id, item.quantity + 1)}
                  >
                    +
                  </button>
                </div>
                <div className="price">${Number(item.line_total).toFixed(2)}</div>
                <button
                  className="link-danger"
                  onClick={() => remove(item.menu_item_id)}
                  aria-label={`Remove ${item.name}`}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>

          <div className="cart-summary">
            <div className="cart-total">
              <span>Subtotal</span>
              <span className="price">${Number(cart.subtotal).toFixed(2)}</span>
            </div>

            <div className="field">
              <label htmlFor="cart-address">Deliver to</label>
              {addresses.length === 0 ? (
                <p className="muted">
                  No address yet. <Link to="/account" className="back-link">Add one in your account →</Link>
                </p>
              ) : (
                <select
                  id="cart-address"
                  className="input"
                  value={addressId ?? ''}
                  onChange={(e) => setAddressId(Number(e.target.value))}
                >
                  {addresses.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label} — {a.line1}, {a.city}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="field">
              <label>Payment method</label>
              <div className="tabs">
                <button type="button" className="tab" data-active={payMethod === 'COD'} onClick={() => setPayMethod('COD')}>
                  Cash on delivery
                </button>
                {/* Without a publishable key there is no card form to show. */}
                {cardAvailable && (
                  <button type="button" className="tab" data-active={payMethod === 'CARD'} onClick={() => setPayMethod('CARD')}>
                    Card (online)
                  </button>
                )}
              </div>
              {payMethod === 'CARD' && (
                <p className="muted" style={{ marginTop: '0.5rem' }}>
                  You'll enter your card details next. The order is only confirmed once the
                  payment goes through.
                </p>
              )}
            </div>

            <Button
              block
              loading={placing}
              disabled={addressId === null}
              onClick={checkout}
            >
              {payMethod === 'CARD' ? 'Place order (Card)' : 'Place order (Cash on Delivery)'}
            </Button>
          </div>
        </>
      )}
    </main>
  )
}
