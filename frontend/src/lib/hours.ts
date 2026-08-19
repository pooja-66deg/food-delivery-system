// Reading a restaurant's opening hours, for the customer-facing surfaces.
//
// The API sends `HH:MM` in the platform's local timezone plus a derived
// `is_accepting_orders`. Everything here is presentation: which row is today,
// how to word it, and when the kitchen next opens — so a "Closed" badge can say
// *until when* instead of leaving the diner to guess.

import type { OpeningHourDay, Restaurant } from '../api/restaurants'

export const DAY_LABELS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const

/** "09:00" -> "9:00 am". Returns the input unchanged if it is not HH:MM. */
export function formatTime(value: string | null): string {
  if (!value) return ''
  const [h, m] = value.split(':')
  const hour = Number(h)
  const minute = Number(m)
  if (Number.isNaN(hour) || Number.isNaN(minute)) return value
  const suffix = hour < 12 ? 'am' : 'pm'
  const display = hour % 12 === 0 ? 12 : hour % 12
  return `${display}:${String(minute).padStart(2, '0')} ${suffix}`
}

/** The seven rows in Monday-first order, with missing days read as closed. */
export function weekRows(hours: OpeningHourDay[]): OpeningHourDay[] {
  const byDay = new Map(hours.map((h) => [h.day_of_week, h]))
  return DAY_LABELS.map((_, day_of_week) => {
    const row = byDay.get(day_of_week)
    return row ?? { day_of_week, opens_at: null, closes_at: null, is_closed: true }
  })
}

/** "9:00 am – 10:00 pm", or "Closed" for a day with no window. */
export function formatWindow(row: OpeningHourDay): string {
  if (row.is_closed || !row.opens_at || !row.closes_at) return 'Closed'
  if (row.opens_at === row.closes_at) return 'Open 24 hours'
  return `${formatTime(row.opens_at)} – ${formatTime(row.closes_at)}`
}

/** One day's window, worded for a compact card summary. */
export function todayLabel(hours: OpeningHourDay[], localDay: number): string {
  if (hours.length === 0) return ''
  const row = weekRows(hours)[localDay]
  return row.is_closed ? 'Closed today' : `Today ${formatWindow(row)}`
}

export type RestaurantAvailability = Pick<
  Restaurant,
  | 'is_open'
  | 'is_accepting_orders'
  | 'opening_hours'
  | 'local_day_of_week'
  | 'current_closes_at'
  | 'open_24_hours'
  | 'next_opens_at'
  | 'next_opens_day'
>

/** Backward-compatible availability while older API payloads lack the derived field. */
export function isAcceptingOrders(restaurant: RestaurantAvailability): boolean {
  return restaurant.is_accepting_orders ?? restaurant.is_open
}

/** Platform-local day supplied by the API; browser day is only legacy fallback. */
export function localDayOfWeek(restaurant: RestaurantAvailability): number {
  return restaurant.local_day_of_week ?? (new Date().getDay() + 6) % 7
}

/** Current close or next opening, using server-derived schedule facts only. */
export function availabilityDetailLabel(restaurant: RestaurantAvailability): string {
  if (isAcceptingOrders(restaurant)) {
    if (restaurant.open_24_hours) return 'Open 24 hours'
    return restaurant.current_closes_at
      ? `Closes at ${formatTime(restaurant.current_closes_at)}`
      : ''
  }
  if (restaurant.next_opens_day == null || !restaurant.next_opens_at) return ''
  const localDay = localDayOfWeek(restaurant)
  const ahead = (restaurant.next_opens_day - localDay + 7) % 7
  const when = ahead === 0
    ? 'today'
    : ahead === 1
      ? 'tomorrow'
      : DAY_LABELS[restaurant.next_opens_day]
  return `Opens ${when} at ${formatTime(restaurant.next_opens_at)}`
}

/** One customer-card line; empty when the owner has not published a schedule. */
export function cardHoursLabel(restaurant: RestaurantAvailability): string {
  const hours = restaurant.opening_hours ?? []
  if (hours.length === 0) return ''
  const today = todayLabel(hours, localDayOfWeek(restaurant))
  const next = isAcceptingOrders(restaurant) ? '' : availabilityDetailLabel(restaurant)
  return `${today}${next ? ` · ${next}` : ''}`
}
