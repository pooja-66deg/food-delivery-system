import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { OpeningHourDay } from '../../api/restaurants'
import { Alert, Button } from '../../components/ui'
import { DAY_LABELS } from '../../lib/hours'

interface OpeningHoursPanelProps {
  restaurantId: number
  /** Current schedule from the API. Empty means none configured. */
  hours: OpeningHourDay[]
  onSaved: () => void
}

const DEFAULT_OPEN = '09:00'
const DEFAULT_CLOSE = '22:00'

function blankWeek(): OpeningHourDay[] {
  return DAY_LABELS.map((_, day_of_week) => ({
    day_of_week,
    opens_at: DEFAULT_OPEN,
    closes_at: DEFAULT_CLOSE,
    is_closed: false,
  }))
}

function fromApi(hours: OpeningHourDay[]): OpeningHourDay[] {
  if (hours.length === 0) return blankWeek()
  const byDay = new Map(hours.map((h) => [h.day_of_week, h]))
  return DAY_LABELS.map((_, day_of_week) => {
    const existing = byDay.get(day_of_week)
    if (!existing) {
      return {
        day_of_week,
        opens_at: DEFAULT_OPEN,
        closes_at: DEFAULT_CLOSE,
        is_closed: true,
      }
    }
    return {
      day_of_week,
      opens_at: existing.opens_at ?? DEFAULT_OPEN,
      closes_at: existing.closes_at ?? DEFAULT_CLOSE,
      is_closed: existing.is_closed,
    }
  })
}

/**
 * Edit the weekly opening schedule.
 *
 * Saves through the same ``restaurantsApi.update`` path as open/close and
 * delivery radius. Clearing the schedule (empty list) restores manual
 * ``is_open``-only behaviour.
 */
export function OpeningHoursPanel({ restaurantId, hours, onSaved }: OpeningHoursPanelProps) {
  const [rows, setRows] = useState(() => fromApi(hours))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const hasSchedule = hours.length > 0
  const openRows = rows.filter((row) => !row.is_closed)
  const dirty = JSON.stringify(rows) !== JSON.stringify(fromApi(hours))
  // The first open day is the one worth copying — an owner filling in a week
  // types one pair of times and repeats it, rather than fourteen inputs.
  const template = openRows[0]

  useEffect(() => setRows(fromApi(hours)), [restaurantId, hours])

  function patchDay(day: number, patch: Partial<OpeningHourDay>) {
    setRows((prev) => prev.map((row) => (row.day_of_week === day ? { ...row, ...patch } : row)))
  }

  function applyTemplateToWeek() {
    if (!template) return
    setRows((prev) =>
      prev.map((row) => ({
        ...row,
        opens_at: template.opens_at,
        closes_at: template.closes_at,
        is_closed: false,
      })),
    )
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaved(false)
    setBusy(true)
    try {
      const opening_hours = rows.map((row) =>
        row.is_closed
          ? { day_of_week: row.day_of_week, opens_at: null, closes_at: null, is_closed: true }
          : {
              day_of_week: row.day_of_week,
              opens_at: row.opens_at,
              closes_at: row.closes_at,
              is_closed: false,
            },
      )
      await restaurantsApi.update(restaurantId, { opening_hours })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Could not update opening hours.'))
    } finally {
      setBusy(false)
    }
  }

  async function clearSchedule() {
    setError(null)
    setSaved(false)
    setBusy(true)
    try {
      await restaurantsApi.update(restaurantId, { opening_hours: [] })
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Could not clear opening hours.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="hours-editor" onSubmit={(e) => void submit(e)}>
      {error && <Alert>{error}</Alert>}
      {saved && !dirty && <Alert kind="ok">Hours saved.</Alert>}

      <div className="hours-editor-head">
        <span className={`badge ${openRows.length > 0 ? 'badge-open' : 'badge-closed'}`}>
          {openRows.length === 0
            ? 'Closed all week'
            : `Open ${openRows.length} of 7 days`}
        </span>
        {!hasSchedule && <span className="chip">Draft — not published</span>}
        {template && (
          <button
            type="button"
            className="hours-editor-copy"
            onClick={applyTemplateToWeek}
            disabled={busy}
          >
            Apply {DAY_LABELS[template.day_of_week]} to every day
          </button>
        )}
      </div>

      <div className="hours-editor-grid" role="group" aria-label="Weekly opening hours">
        {/* Column captions once, rather than a label over all fourteen inputs. */}
        <div className="hours-editor-columns" aria-hidden="true">
          <span>Day</span>
          <span>Opens</span>
          <span>Closes</span>
        </div>

        {rows.map((row) => {
          const label = DAY_LABELS[row.day_of_week]
          return (
            <div
              key={row.day_of_week}
              className={`hours-editor-row${row.is_closed ? ' hours-editor-row-closed' : ''}`}
            >
              <label className="hours-switch">
                <input
                  type="checkbox"
                  checked={!row.is_closed}
                  aria-label={`${label} open`}
                  onChange={(e) => patchDay(row.day_of_week, { is_closed: !e.target.checked })}
                />
                <span className="hours-switch-track" aria-hidden="true" />
                <span className="hours-switch-day">{label}</span>
              </label>

              {row.is_closed ? (
                <span className="hours-editor-closed">Closed</span>
              ) : (
                <>
                  <input
                    className="input hours-editor-time"
                    type="time"
                    aria-label={`${label} opens at`}
                    value={row.opens_at ?? DEFAULT_OPEN}
                    onChange={(e) => patchDay(row.day_of_week, { opens_at: e.target.value })}
                  />
                  <input
                    className="input hours-editor-time"
                    type="time"
                    aria-label={`${label} closes at`}
                    value={row.closes_at ?? DEFAULT_CLOSE}
                    onChange={(e) => patchDay(row.day_of_week, { closes_at: e.target.value })}
                  />
                </>
              )}
            </div>
          )
        })}
      </div>

      <div className="hours-editor-actions">
        <Button loading={busy}>Save hours</Button>
        {hasSchedule && (
          <Button
            type="button"
            variant="ghost"
            loading={busy}
            onClick={() => void clearSchedule()}
          >
            Clear schedule
          </Button>
        )}
      </div>
    </form>
  )
}
