import { describe, expect, it } from 'vitest'

import {
  availabilityDetailLabel,
  cardHoursLabel,
  formatTime,
  formatWindow,
  todayLabel,
  weekRows,
} from '../../src/lib/hours'
import type { OpeningHourDay, Restaurant } from '../../src/api/restaurants'

function day(
  day_of_week: number,
  opens_at: string | null = '09:00',
  closes_at: string | null = '22:00',
  is_closed = false,
): OpeningHourDay {
  return { day_of_week, opens_at, closes_at, is_closed }
}

describe('hours helpers', () => {
  it('formats times for reading, not for input fields', () => {
    expect(formatTime('09:00')).toBe('9:00 am')
    expect(formatTime('22:30')).toBe('10:30 pm')
    expect(formatTime('00:15')).toBe('12:15 am')
    expect(formatTime('12:00')).toBe('12:00 pm')
    expect(formatTime(null)).toBe('')
  })

  it('fills a partial schedule with closed days rather than dropping them', () => {
    const rows = weekRows([day(0), day(1)])

    expect(rows).toHaveLength(7)
    expect(rows[6].is_closed).toBe(true)
    expect(formatWindow(rows[6])).toBe('Closed')
  })

  it('reads equal open and close as all day', () => {
    expect(formatWindow(day(0, '00:00', '00:00'))).toBe('Open 24 hours')
  })

  it('summarises today, and says so when today is closed', () => {
    const open = [day(2, '10:00', '20:00')]
    expect(todayLabel(open, 2)).toBe('Today 10:00 am – 8:00 pm')

    const closed = [day(2, null, null, true)]
    expect(todayLabel(closed, 2)).toBe('Closed today')
  })

  it('formats server-derived availability without recalculating the schedule', () => {
    const open = {
      is_open: true,
      is_accepting_orders: true,
      current_closes_at: '20:00',
    } as Restaurant
    expect(availabilityDetailLabel(open)).toBe('Closes at 8:00 pm')

    const tomorrow = {
      is_open: true,
      is_accepting_orders: false,
      local_day_of_week: 2,
      next_opens_day: 3,
      next_opens_at: '09:00',
    } as Restaurant
    expect(availabilityDetailLabel(tomorrow)).toBe('Opens tomorrow at 9:00 am')
  })

  it('builds the customer card label from API timing metadata', () => {
    const restaurant = {
      is_open: true,
      is_accepting_orders: false,
      opening_hours: [day(2, null, null, true), day(4, '11:00', '15:00')],
      local_day_of_week: 2,
      next_opens_day: 4,
      next_opens_at: '11:00',
    } as Restaurant
    expect(cardHoursLabel(restaurant)).toBe('Closed today · Opens Friday at 11:00 am')
  })
})
