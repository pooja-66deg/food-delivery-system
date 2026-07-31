import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { ordersApi } from '../api/orders'
import type { Order } from '../api/orders'
import { restaurantsApi } from '../api/restaurants'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button } from '../components/ui'
import { OrderOps } from '../components/OrderOps'

export function RestaurantOrdersPage() {
  const { user } = useAuth()
  const [orders, setOrders] = useState<Order[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isOwner = user?.role === 'restaurant' || user?.role === 'admin'

  const load = useCallback(async () => {
    if (!isOwner || !user) return
    setError(null)
    try {
      const all = await restaurantsApi.list()
      const mine = all.filter((r) => r.owner_id === user.id || user.role === 'admin')
      const lists = await Promise.all(mine.map((r) => ordersApi.forRestaurant(r.id).catch(() => [])))
      const merged = lists.flat().sort((a, b) => b.id - a.id)
      setOrders(merged)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load orders.')
    }
  }, [isOwner, user])

  useEffect(() => {
    void load()
  }, [load])

  if (!isOwner) {
    return (
      <main className="app-main">
        <h1>Orders</h1>
        <div className="empty">This area is for restaurant accounts.</div>
      </main>
    )
  }

  return (
    <main className="app-main">
      <div className="owner-head">
        <h1>Orders</h1>
        <Button variant="ghost" onClick={load}>Refresh</Button>
      </div>
      {error && <Alert>{error}</Alert>}
      {!orders ? (
        <div className="empty"><span className="spin" aria-hidden /> Loading…</div>
      ) : (
        <OrderOps orders={orders} onChanged={load} />
      )}
    </main>
  )
}
