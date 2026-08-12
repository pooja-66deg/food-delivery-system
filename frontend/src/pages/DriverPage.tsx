import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../api/client'
import { deliveryApi } from '../api/delivery'
import type { Coordinate, Delivery } from '../api/delivery'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, EmptyState, Loading } from '../components/ui'
import { useDriverLocation } from '../lib/useDriverLocation'
import { useNotifications } from '../notifications/NotificationsContext'

const DESCRIPTIONS: Record<string, string> = {
  ASSIGNED: 'Offered to you — accept to take it',
  ACCEPTED: 'Accepted — head to the restaurant',
  PICKED_UP: 'On the way to the customer',
}

const SHARE_STATUS: Record<string, string> = {
  off: 'Not sharing. Turn this on to receive nearby orders.',
  sharing: 'Sharing your location',
  denied: 'Location permission is blocked. Enable it in your browser to share your position.',
  unavailable: 'Your position is unavailable right now.',
  unsupported: 'This device cannot share a location.',
}

/** Before pickup the driver heads to the restaurant; after it, to the customer. */
function nextStop(d: Delivery): Coordinate | null {
  return d.status === 'PICKED_UP' ? d.destination : d.restaurant
}

function navigateUrl(point: Coordinate): string {
  // A plain maps URL — no API key, no SDK, and it opens the native app on a
  // phone rather than a web map.
  return `https://www.google.com/maps/dir/?api=1&destination=${point.latitude},${point.longitude}`
}

export function DriverPage() {
  const { user } = useAuth()
  const { refresh: refreshNotifications } = useNotifications()
  const share = useDriverLocation()
  const [assignments, setAssignments] = useState<Delivery[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [actingOn, setActingOn] = useState<{ orderId: number; action: string } | null>(null)

  const isDriver = user?.role === 'driver' || user?.role === 'admin'

  const load = useCallback(async () => {
    if (!isDriver) return
    setError(null)
    try {
      setAssignments(await deliveryApi.assignments())
      void refreshNotifications()
    } catch (e) {
      setError(errorMessage(e, 'Failed to load assignments.'))
    }
  }, [isDriver, refreshNotifications])

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
    setActingOn({ orderId, action })
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

      <div className="share-card">
        <button
          type="button"
          role="switch"
          aria-checked={share.sharing}
          aria-label="Share my location"
          className="share-switch"
          data-on={share.sharing}
          disabled={share.status === 'unsupported'}
          onClick={() => (share.sharing ? void share.disable() : void share.enable())}
        >
          <span className="share-knob" aria-hidden />
        </button>
        <div>
          <div className="menu-item-name">Share my location</div>
          <div className="muted">
            {SHARE_STATUS[share.status]}
            {share.lastUpdate
              ? ` · updated ${new Date(share.lastUpdate).toLocaleTimeString()}`
              : ''}
          </div>
        </div>
      </div>

      {share.error && <Alert>{share.error}</Alert>}
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
                {nextStop(d) && (
                  <a
                    className="link-inline"
                    href={navigateUrl(nextStop(d)!)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Navigate
                  </a>
                )}
                {d.status === 'ASSIGNED' && (
                  <>
                    <Button loading={actingOn?.orderId === d.order_id && actingOn?.action === 'accept'} onClick={() => act(d.order_id, 'accept')}>
                      Accept
                    </Button>
                    <Button variant="ghost" loading={actingOn?.orderId === d.order_id && actingOn?.action === 'reject'} onClick={() => act(d.order_id, 'reject')}>
                      Reject
                    </Button>
                  </>
                )}
                {d.status === 'ACCEPTED' && (
                  <Button loading={actingOn?.orderId === d.order_id && actingOn?.action === 'pickup'} onClick={() => act(d.order_id, 'pickup')}>
                    Pick up
                  </Button>
                )}
                {d.status === 'PICKED_UP' && (
                  <Button loading={actingOn?.orderId === d.order_id && actingOn?.action === 'deliver'} onClick={() => act(d.order_id, 'deliver')}>
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
