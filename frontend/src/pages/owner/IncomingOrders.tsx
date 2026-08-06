import type { Order } from '../../api/orders'
import { EmptyState } from '../../components/ui'
import { OrderTicket } from './OrderTicket'

interface IncomingOrdersProps {
  /** Every owned restaurant's orders, already merged and newest first. */
  orders: Order[]
  /** Restaurant id → name, so a ticket can say which kitchen it is for. */
  names: Map<number, string>
  now: Date
  onChanged: () => void | Promise<void>
}

/**
 * The dashboard's ticket rail.
 *
 * Presentational: the page fetches and merges orders across restaurants, because
 * the stat tiles need the same data and fetching it twice would let the two
 * disagree.
 */
export function IncomingOrders({ orders, names, now, onChanged }: IncomingOrdersProps) {
  if (orders.length === 0) {
    return <EmptyState>Nothing in the queue. New orders land here as they come in.</EmptyState>
  }

  return (
    <div className="ticket-rail">
      {orders.map((order) => (
        <OrderTicket
          key={order.id}
          order={order}
          restaurantName={names.get(order.restaurant_id) ?? 'Your kitchen'}
          now={now}
          onChanged={onChanged}
        />
      ))}
    </div>
  )
}
