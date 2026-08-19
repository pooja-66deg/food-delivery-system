import { useState } from 'react'

import {
  DAY_LABELS,
  availabilityDetailLabel,
  cardHoursLabel,
  formatWindow,
  isAcceptingOrders,
  localDayOfWeek,
  weekRows,
} from '../lib/hours'
import type { RestaurantAvailability } from '../lib/hours'
import { Modal } from './ui'

/** The open/closed badge shared by browse and favourites cards. */
export function RestaurantAvailabilityBadge(
  { restaurant }: { restaurant: RestaurantAvailability },
) {
  const accepting = isAcceptingOrders(restaurant)
  return (
    <span className={`badge ${accepting ? 'badge-open' : 'badge-closed'}`}>
      {accepting ? 'Open' : 'Closed'}
    </span>
  )
}

/** Today's hours and next opening, shared by browse and favourites cards. */
export function RestaurantCardHours({ restaurant }: { restaurant: RestaurantAvailability }) {
  const label = cardHoursLabel(restaurant)
  return label ? <p className="muted card-hours">{label}</p> : null
}

/** Compact detail-page timing control plus the complete weekly schedule modal. */
export function RestaurantTimingControl(
  { restaurant }: { restaurant: RestaurantAvailability },
) {
  const [open, setOpen] = useState(false)
  const hours = restaurant.opening_hours ?? []
  const accepting = isAcceptingOrders(restaurant)
  const status = accepting ? 'Open now' : 'Closed'
  const detail = availabilityDetailLabel(restaurant)
  const summaryLabel = `${status}${detail ? ` · ${detail}` : ''} — View timings`
  const today = localDayOfWeek(restaurant)

  return (
    <>
      <button
        type="button"
        className="hours-summary"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={summaryLabel}
      >
        <span className={accepting ? 'hours-summary-open' : 'hours-summary-closed'}>
          {status}
        </span>
        {detail && <span aria-hidden="true">·</span>}
        {detail && <span>{detail}</span>}
        <span className="hours-summary-chevron" aria-hidden="true">⌄</span>
      </button>

      <Modal open={open} title="Restaurant timings" onClose={() => setOpen(false)}>
        {hours.length === 0 ? (
          <p className="muted hours-unpublished">
            This restaurant has not published its weekly timings yet. It takes orders
            whenever it is manually marked open.
          </p>
        ) : (
          <ul className="hours-list">
            {weekRows(hours).map((row) => {
              const isToday = row.day_of_week === today
              return (
                <li
                  key={row.day_of_week}
                  className={`hours-row${isToday ? ' hours-row-today' : ''}`}
                  aria-current={isToday ? 'date' : undefined}
                >
                  <span className="hours-day">
                    {DAY_LABELS[row.day_of_week]}
                    {isToday && <span className="hours-today-tag">Today</span>}
                  </span>
                  <span className={`hours-window${row.is_closed ? ' hours-window-closed' : ''}`}>
                    {formatWindow(row)}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </Modal>
    </>
  )
}
