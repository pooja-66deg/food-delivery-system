// Derivations behind the manage dashboard's tiles and badges.
//
// Kept as pure functions taking `now` explicitly rather than reading the clock:
// "today" and "3 min ago" are the parts most likely to be wrong at a month
// boundary or in another timezone, and this way they can be tested.

import type { Order } from '../../api/orders'
import type { RestaurantDetail } from '../../api/restaurants'

/**
 * Statuses where the kitchen still owes the diner something.
 *
 * Stops at READY_FOR_PICKUP: once a driver has it, it is no longer the
 * restaurant's to act on, so counting it as a live order would overstate what
 * the owner has to deal with.
 */
const LIVE_STATUSES = new Set([
  'PAYMENT_SUCCESS',
  'RESTAURANT_ACCEPTED',
  'PREPARING',
  'READY_FOR_PICKUP',
])

/** Orders that never reached the kitchen, so they do not count as trade. */
const DEAD_STATUSES = new Set(['CANCELLED', 'REJECTED', 'PAYMENT_PENDING', 'CREATED'])

/** At or below this count, an item is worth warning the owner about. */
export const LOW_STOCK_THRESHOLD = 3

export function isLiveOrder(order: Order): boolean {
  return LIVE_STATUSES.has(order.status)
}

export function isSameDay(iso: string, now: Date): boolean {
  const at = new Date(iso)
  return (
    at.getFullYear() === now.getFullYear() &&
    at.getMonth() === now.getMonth() &&
    at.getDate() === now.getDate()
  )
}

/** Today's takings: what was actually ordered, excluding cancelled and unpaid. */
export function orderValueToday(orders: Order[], now: Date): number {
  return orders
    .filter((o) => isSameDay(o.created_at, now) && !DEAD_STATUSES.has(o.status))
    .reduce((sum, o) => sum + Number(o.total), 0)
}

/** Dishes running out. Untracked stock (null) is not low, it is unknown. */
export function lowStockCount(detail: RestaurantDetail): number {
  return detail.menu
    .flatMap((cat) => cat.items)
    .filter((item) => item.stock_quantity !== null && item.stock_quantity <= LOW_STOCK_THRESHOLD)
    .length
}

export function categoryCount(detail: RestaurantDetail): number {
  return detail.menu.length
}

export function dishCount(detail: RestaurantDetail): number {
  return detail.menu.reduce((n, cat) => n + cat.items.length, 0)
}

/**
 * How long ago something happened, in the coarsest unit that is still useful.
 *
 * A kitchen cares about minutes, so anything under an hour stays in minutes
 * rather than rounding to "an hour ago" and losing the urgency.
 */
export function timeAgo(iso: string, now: Date): string {
  const seconds = Math.floor((now.getTime() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hr ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

/** Pluralises a count with its noun: 4 → "4 items", 1 → "1 item". */
export function plural(count: number, noun: string, pluralNoun = `${noun}s`): string {
  return `${count} ${count === 1 ? noun : pluralNoun}`
}
