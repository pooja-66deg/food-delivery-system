import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../api/client'
import { deliveryApi } from '../api/delivery'
import type { Delivery } from '../api/delivery'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, EmptyState, Loading } from '../components/ui'

const DESCRIPTIONS: Record<string, string> = {
  ASSIGNED: 'Offered to you — accept to take it',
  ACCEPTED: 'Accepted — head to the restaurant',
  PICKED_UP: 'On the way to the customer',
}

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
      setError(errorMessage(e, 'Failed to load assignments.'))
    }
  }, [isDriver])

  useEffect(() => {
    void load()
  }, [load])

  const MESSAGES: Record<string, string> = {
    accept: 'Accepted order',
    reject: 'Released order',
    pickup: 'Picked up order',
    deliver: 'Delivered order',
  }

  async function act(orderId: number, action: 'accept' | 'reject' | 'pickup' | 'deliver') {
    setError(null)
    setNotice(null)
    setActingOn(orderId)
    try {
      await deliveryApi[action](orderId)
      setNotice(`${MESSAGES[action]} #${orderId}.`)
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Action failed.'))
    } finally {
      setActingOn(null)
    }
  }

  if (!isDriver) {
    return (
      <main className="app-main">
        <h1>Deliveries</h1>
        <EmptyState>This area is for driver accounts.</EmptyState>
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
        <Loading />
      ) : assignments.length === 0 ? (
        <EmptyState>No active deliveries. New orders are assigned when a restaurant marks them ready.</EmptyState>
      ) : (
        <div className="order-list">
          {assignments.map((d) => (
            <div key={d.id} className="delivery-card">
              <div>
                <div className="menu-item-name">Order #{d.order_id}</div>
                <div className="muted">{DESCRIPTIONS[d.status] ?? d.status}</div>
              </div>
              <span className="badge">{d.status}</span>
              <div className="delivery-actions">
                {d.status === 'ASSIGNED' && (
                  <>
                    <Button loading={actingOn === d.order_id} onClick={() => act(d.order_id, 'accept')}>
                      Accept
                    </Button>
                    <Button variant="ghost" loading={actingOn === d.order_id} onClick={() => act(d.order_id, 'reject')}>
                      Reject
                    </Button>
                  </>
                )}
                {d.status === 'ACCEPTED' && (
                  <Button loading={actingOn === d.order_id} onClick={() => act(d.order_id, 'pickup')}>
                    Pick up
                  </Button>
                )}
                {d.status === 'PICKED_UP' && (
                  <Button loading={actingOn === d.order_id} onClick={() => act(d.order_id, 'deliver')}>
                    Mark delivered
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
