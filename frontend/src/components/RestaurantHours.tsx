import { useState } from 'react'

import {
  DAY_LABELS,
  availabilityDetailLabel,
  availabilityStatusLabel,
  cardHoursLabel,
  closedReason,
  closedStatusExplanation,
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
  const status = availabilityStatusLabel(restaurant)
  const detail = availabilityDetailLabel(restaurant)
  const explanation = closedStatusExplanation(restaurant)
  const manuallyPaused = closedReason(restaurant) === 'manual'
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
        {!accepting && explanation && (
          <div className="hours-status-banner" role="status">
            <strong>{status}</strong>
            <p>{explanation}</p>
            {detail && <p className="hours-status-next">{detail}</p>}
          </div>
        )}
        {hours.length === 0 ? (
          <p className="muted hours-unpublished">
            This restaurant has not published its weekly timings yet. It takes orders
            whenever it is manually marked open.
          </p>
        ) : (
          <ul className="hours-list">
            {weekRows(hours).map((row) => {
              const isToday = row.day_of_week === today
              const hasWindow = !row.is_closed && Boolean(row.opens_at)
              // A manual pause overrides today's published window, so the row
              // leads with the live state and keeps the schedule as context.
              const pausedToday = isToday && manuallyPaused && hasWindow
              const showScheduledHint = isToday && !accepting && !manuallyPaused && hasWindow
              return (
                <li
                  key={row.day_of_week}
                  className={`hours-row${isToday ? ' hours-row-today' : ''}${
                    isToday && !accepting ? ' hours-row-today-closed' : ''
                  }`}
                  aria-current={isToday ? 'date' : undefined}
                >
                  <span className="hours-day">
                    {DAY_LABELS[row.day_of_week]}
                    {isToday && (
                      <span
                        className={`hours-today-tag${accepting ? '' : ' hours-today-tag-closed'}`}
                      >
                        Today
                      </span>
                    )}
                  </span>
                  <span className={`hours-window${row.is_closed ? ' hours-window-closed' : ''}`}>
                    {pausedToday ? (
                      <>
                        <span className="hours-window-status">Currently closed</span>
                        <span className="hours-window-scheduled">
                          {formatWindow(row)} (scheduled)
                        </span>
                      </>
                    ) : (
                      <>
                        {formatWindow(row)}
                        {showScheduledHint && (
                          <span className="hours-scheduled-hint"> (scheduled)</span>
                        )}
                      </>
                    )}
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
