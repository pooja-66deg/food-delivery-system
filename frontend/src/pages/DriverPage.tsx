import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { deliveryApi } from '../api/delivery'
import type { Delivery } from '../api/delivery'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button } from '../components/ui'

export function DriverPage() {
  const { user } = useAuth()
  const [assignments, setAssignments] = useState<Delivery[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [actingOn, setActingOn] = useState<number | null>(null)

  const isDriver = user?.role === 'driver' || user?.role === 'admin'

  const load = useCallback(async () => {
    if (!isDriver) return
    setError(null)
    try {
      setAssignments(await deliveryApi.assignments())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load assignments.')
    }
  }, [isDriver])

  useEffect(() => {
    void load()
  }, [load])

  async function act(orderId: number, action: 'pickup' | 'deliver') {
    setError(null)
    setNotice(null)
    setActingOn(orderId)
    try {
      await deliveryApi[action](orderId)
      setNotice(action === 'pickup' ? `Picked up order #${orderId}.` : `Delivered order #${orderId}.`)
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Action failed.')
    } finally {
      setActingOn(null)
    }
  }

  if (!isDriver) {
    return (
      <main className="app-main">
        <h1>Deliveries</h1>
        <div className="empty">This area is for driver accounts.</div>
      </main>
    )
  }

  return (
    <main className="app-main">
      <div className="owner-head">
        <h1>Your deliveries</h1>
        <Button variant="ghost" onClick={load}>Refresh</Button>
      </div>

      {error && <Alert>{error}</Alert>}
      {notice && <Alert kind="ok">{notice}</Alert>}

      {!assignments ? (
        <div className="empty"><span className="spin" aria-hidden /> Loading…</div>
      ) : assignments.length === 0 ? (
        <div className="empty">No active deliveries. New orders are assigned when a restaurant marks them ready.</div>
      ) : (
        <div className="order-list">
          {assignments.map((d) => (
            <div key={d.id} className="order-card" style={{ cursor: 'default' }}>
              <div>
                <div className="menu-item-name">Order #{d.order_id}</div>
                <div className="muted">
                  {d.status === 'ASSIGNED' ? 'Ready for pickup' : 'Out for delivery'}
                </div>
              </div>
              <span className="badge">{d.status === 'ASSIGNED' ? 'Assigned' : 'Picked up'}</span>
              {d.status === 'ASSIGNED' ? (
                <Button loading={actingOn === d.order_id} onClick={() => act(d.order_id, 'pickup')}>
                  Pick up
                </Button>
              ) : (
                <Button loading={actingOn === d.order_id} onClick={() => act(d.order_id, 'deliver')}>
                  Mark delivered
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
