import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { errorMessage } from '../api/client'
import { ordersApi } from '../api/orders'
import type { OrderSummary } from '../api/orders'
import { Alert, EmptyState, Loading } from '../components/ui'
import { statusLabel } from './orderStatus'

export function OrdersPage() {
  const [orders, setOrders] = useState<OrderSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ordersApi
      .list()
      .then(setOrders)
      .catch((e) => setError(errorMessage(e, 'Failed to load orders.')))
  }, [])

  if (error) {
    return (
      <main className="app-main">
        <h1>Your orders</h1>
        <Alert>{error}</Alert>
      </main>
    )
  }

  if (!orders) {
    return (
      <main className="app-main">
        <Loading />
      </main>
    )
  }

  return (
    <main className="app-main">
      <h1>Your orders</h1>
      {orders.length === 0 ? (
        <EmptyState>
          No orders yet. <Link to="/restaurants" className="back-link">Order something →</Link>
        </EmptyState>
      ) : (
        <div className="order-list">
          {orders.map((o) => (
            <Link key={o.id} to={`/orders/${o.id}`} className="order-card">
              <div>
                <div className="menu-item-name">Order #{o.id}</div>
                <div className="muted">{new Date(o.created_at).toLocaleString()}</div>
              </div>
              <span className="badge">{statusLabel(o.status)}</span>
              <div className="price">${Number(o.total).toFixed(2)}</div>
            </Link>
          ))}
        </div>
      )}
    </main>
  )
}
