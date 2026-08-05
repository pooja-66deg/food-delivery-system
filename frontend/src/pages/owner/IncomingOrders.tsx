import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { ordersApi } from '../../api/orders'
import type { Order } from '../../api/orders'
import { Alert, Button, Loading } from '../../components/ui'
import { OrderOps } from '../../components/OrderOps'

export function IncomingOrders({ restaurantId }: { restaurantId: number }) {
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setOrders(await ordersApi.forRestaurant(restaurantId))
    } catch (e) {
      setError(errorMessage(e, 'Failed to load orders.'))
    }
  }, [restaurantId])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section className="menu-section">
      <div className="owner-head">
        <h2>Incoming orders</h2>
        <Button variant="ghost" onClick={load}>Refresh</Button>
      </div>
      {error && <Alert>{error}</Alert>}

      {!orders ? (
        <Loading />
      ) : orders.length === 0 ? (
        <p className="muted">No incoming orders.</p>
      ) : (
        <div>
          {orders.map((order) => (
            <div key={order.id} className="order-card">
              <div className="order-card-header">
                <div>
                  <div className="order-card-title">Order #{order.id}</div>
                  <div className="order-card-time">{new Date(order.created_at).toLocaleString()}</div>
                </div>
                <div className="order-card-total">${Number(order.total).toFixed(2)}</div>
              </div>

              <div className="order-card-items">
                {order.items.map((item, i) => (
                  <div key={i}>{item.name} × {item.quantity}</div>
                ))}
              </div>

              <div className="order-card-footer">
                <span className="badge">{order.status}</span>
                <OrderOps orders={[order]} onChanged={load} />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
