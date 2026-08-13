import { useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { ordersApi } from '../../api/orders'
import type { Order } from '../../api/orders'
import { deliveryApi, type Delivery, type Driver } from '../../api/delivery'
import { Alert, Button, Modal } from '../../components/ui'
import { statusLabel } from '../orderStatus'
import { timeAgo } from './ownerStats'

interface OrderTicketProps {
  order: Order
  /** Which kitchen it is for — the dashboard mixes every restaurant's orders. */
  restaurantName: string
  now: Date
  onChanged: () => void | Promise<void>
}

/**
 * One order as a kitchen ticket: who it is for, what is on it, and the single
 * next thing to do with it.
 *
 * The action set is deliberately the *next* step only. A row of every possible
 * transition invites an owner to mark an order ready before it is cooked.
 */
export function OrderTicket({ order, restaurantName, now, onChanged }: OrderTicketProps) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [delivery, setDelivery] = useState<Delivery | null>(null)
  const [drivers, setDrivers] = useState<Driver[] | null>(null)
  const [showChangeDriver, setShowChangeDriver] = useState(false)
  const [changingDriver, setChangingDriver] = useState(false)

  useEffect(() => {
    if (order.status === 'READY_FOR_PICKUP') {
      void loadDelivery()
    }
  }, [order.status])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      await onChanged()
    } catch (e) {
      setError(errorMessage(e, 'Action failed.'))
    } finally {
      setBusy(false)
    }
  }

  async function markReady() {
    await run(async () => {
      await ordersApi.setStatus(order.id, 'READY_FOR_PICKUP')
      const availableDrivers = await deliveryApi.availableDrivers()
      setDrivers(availableDrivers)
    })
  }

  async function changeDriver(driverId: number) {
    setChangingDriver(true)
    setError(null)
    try {
      await deliveryApi.reassign(order.id, driverId)
      setShowChangeDriver(false)
      await onChanged()
    } catch (e) {
      setError(errorMessage(e, 'Failed to reassign driver.'))
    } finally {
      setChangingDriver(false)
    }
  }

  async function loadDelivery() {
    try {
      const tracking = await deliveryApi.tracking(order.id)
      setDelivery({
        id: 0,
        order_id: order.id,
        driver_id: tracking.driver_id,
        status: tracking.status,
        restaurant_name: null,
        assigned_at: null,
        picked_up_at: null,
        delivered_at: null,
        restaurant: tracking.restaurant,
        destination: tracking.destination,
      })
    } catch (e) {
      console.error('Failed to load delivery:', e)
    }
  }

  const itemTotal = order.items.reduce((n, i) => n + i.quantity, 0)

  return (
    <article className="ticket">
      <div className="ticket-head">
        <div>
          <h3 className="ticket-title">
            #{order.id} · {restaurantName}
          </h3>
          <p className="muted ticket-meta">
            {timeAgo(order.created_at, now)} · {order.payment_method === 'COD' ? 'Cash' : 'Card'} ·{' '}
            {itemTotal === 1 ? '1 item' : `${itemTotal} items`}
          </p>
        </div>
        <span className={`ticket-status status-${order.status.toLowerCase()}`}>
          {statusLabel(order.status)}
        </span>
      </div>

      <ul className="ticket-lines">
        {order.items.map((item, i) => (
          <li key={i}>
            <span className="ticket-line-name">
              {item.quantity} × {item.name}
            </span>
            <span className="ticket-line-price">₹{Number(item.line_total).toFixed(2)}</span>
          </li>
        ))}
      </ul>

      {error && <Alert>{error}</Alert>}

      {order.status === 'READY_FOR_PICKUP' && delivery && (
        <div className="ticket-driver">
          <div>
            <div className="ticket-driver-label">Assigned driver</div>
            <div className="ticket-driver-name">{delivery.driver_id ? `Driver #${delivery.driver_id}` : 'No driver assigned'}</div>
          </div>
          <Button variant="ghost" onClick={() => {
            setShowChangeDriver(true)
            if (drivers === null) {
              void (async () => {
                try {
                  const avail = await deliveryApi.availableDrivers()
                  setDrivers(avail)
                } catch (e) {
                  setError(errorMessage(e, 'Failed to load drivers.'))
                }
              })()
            }
          }}>
            Change
          </Button>
        </div>
      )}

      <div className="ticket-foot">
        <span className="ticket-total">₹{Number(order.total).toFixed(2)}</span>
        <div className="ticket-actions">
          {order.status === 'PAYMENT_SUCCESS' && (
            <>
              <Button variant="ghost" loading={busy} onClick={() => run(() => ordersApi.reject(order.id))}>
                Reject
              </Button>
              <Button loading={busy} onClick={() => run(() => ordersApi.accept(order.id))}>
                Accept
              </Button>
            </>
          )}
          {order.status === 'RESTAURANT_ACCEPTED' && (
            <Button loading={busy} onClick={() => run(() => ordersApi.setStatus(order.id, 'PREPARING'))}>
              Start
            </Button>
          )}
          {order.status === 'PREPARING' && (
            <Button
              loading={busy}
              onClick={() => markReady()}
            >
              Mark ready
            </Button>
          )}
        </div>
      </div>

      <Modal
        open={showChangeDriver}
        title="Select a driver"
        onClose={() => setShowChangeDriver(false)}
      >
        {drivers === null ? (
          <div style={{ padding: '1rem' }}>Loading drivers...</div>
        ) : drivers.length === 0 ? (
          <div style={{ padding: '1rem' }}>No drivers available.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {drivers.map((driver) => (
              <Button
                key={driver.id}
                variant="ghost"
                loading={changingDriver}
                onClick={() => void changeDriver(driver.id)}
                style={{ justifyContent: 'flex-start', padding: '0.75rem' }}
              >
                {driver.first_name} {driver.last_name}
              </Button>
            ))}
          </div>
        )}
      </Modal>
    </article>
  )
}
