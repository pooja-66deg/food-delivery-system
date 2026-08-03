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
      {!orders ? <Loading /> : <OrderOps orders={orders} onChanged={load} />}
    </section>
  )
}
