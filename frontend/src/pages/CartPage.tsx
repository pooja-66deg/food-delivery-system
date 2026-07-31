import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { authApi } from '../api/auth'
import type { Address } from '../api/auth'
import { ApiError } from '../api/client'
import { ordersApi } from '../api/orders'
import type { PaymentMethod } from '../api/orders'
import { useCart } from '../cart/CartContext'
import { Alert, Button } from '../components/ui'

export function CartPage() {
  const { cart, refresh, update, remove } = useCart()
  const navigate = useNavigate()
  const [addresses, setAddresses] = useState<Address[]>([])
  const [addressId, setAddressId] = useState<number | null>(null)
  const [payMethod, setPayMethod] = useState<PaymentMethod>('COD')
  const [error, setError] = useState<string | null>(null)
  const [placing, setPlacing] = useState(false)

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
      navigate(`/orders/${order.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Checkout failed.')
    } finally {
      setPlacing(false)
    }
  }

  const empty = !cart || cart.items.length === 0

  return (
    <main className="app-main">
      <h1>Your cart</h1>

      {error && <Alert>{error}</Alert>}

      {empty ? (
        <div className="empty">
          Your cart is empty. <Link to="/restaurants" className="back-link">Browse restaurants →</Link>
        </div>
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
                <button type="button" className="tab" data-active={payMethod === 'CARD'} onClick={() => setPayMethod('CARD')}>
                  Card (online)
                </button>
              </div>
              {payMethod === 'CARD' && (
                <p className="muted" style={{ marginTop: '0.5rem' }}>
                  Card is processed via Stripe. In this demo the card step is simulated unless Stripe keys are configured.
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
