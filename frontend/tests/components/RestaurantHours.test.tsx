import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { OpeningHourDay, Restaurant } from '../../src/api/restaurants'
import { RestaurantTimingControl } from '../../src/components/RestaurantHours'

function day(
  day_of_week: number,
  opens_at: string | null = '09:00',
  closes_at: string | null = '22:00',
  is_closed = false,
): OpeningHourDay {
  return { day_of_week, opens_at, closes_at, is_closed }
}

function restaurant(
  overrides: Partial<Restaurant> = {},
): Pick<
  Restaurant,
  | 'is_open'
  | 'is_accepting_orders'
  | 'opening_hours'
  | 'local_day_of_week'
  | 'current_closes_at'
  | 'open_24_hours'
  | 'next_opens_at'
  | 'next_opens_day'
> {
  return {
    is_open: true,
    is_accepting_orders: true,
    opening_hours: [0, 1, 2, 3, 4, 5, 6].map((value) => day(value)),
    local_day_of_week: 2,
    current_closes_at: '22:00',
    open_24_hours: false,
    next_opens_at: null,
    next_opens_day: null,
    ...overrides,
  }
}

describe('RestaurantTimingControl', () => {
  it('keeps the week in a modal until the diner asks for timings', () => {
    render(<RestaurantTimingControl restaurant={restaurant()} />)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Open now.*View timings/ }))
    expect(screen.getByRole('heading', { name: 'Restaurant timings' })).toBeInTheDocument()
    expect(screen.getByText('Monday')).toBeInTheDocument()
    expect(screen.getByText('Sunday')).toBeInTheDocument()
    expect(screen.getAllByText('9:00 am – 10:00 pm')).toHaveLength(7)
  })

  it('marks the API-provided local day as today', () => {
    render(<RestaurantTimingControl restaurant={restaurant()} />)

    fireEvent.click(screen.getByRole('button', { name: /Open now.*View timings/ }))
    expect(screen.getByText('Today').closest('li')).toHaveTextContent('Wednesday')
  })

  it('uses server-derived closing and next-opening facts', () => {
    const { rerender } = render(<RestaurantTimingControl restaurant={restaurant()} />)
    expect(screen.getByRole('button', { name: /Open now · Closes at 10:00 pm/ }))
      .toBeInTheDocument()

    rerender(
      <RestaurantTimingControl
        restaurant={restaurant({
          is_accepting_orders: false,
          current_closes_at: null,
          next_opens_at: '09:00',
          next_opens_day: 3,
        })}
      />,
    )
    expect(
      screen.getByRole('button', { name: /Outside opening hours · Opens tomorrow at 9:00 am/ }),
    ).toBeInTheDocument()
  })

  it('explains manual closed separately from scheduled hours in the modal', () => {
    render(
      <RestaurantTimingControl
        restaurant={restaurant({
          is_open: false,
          is_accepting_orders: false,
          current_closes_at: null,
          next_opens_at: '09:00',
          next_opens_day: 3,
        })}
      />,
    )

    fireEvent.click(
      screen.getByRole('button', { name: /Currently closed · Usual hours resume tomorrow/ }),
    )
    expect(screen.getByRole('status')).toHaveTextContent(/paused orders/i)

    const todayRow = screen.getByText('Today').closest('li')
    expect(todayRow).toHaveTextContent('Wednesday')
    expect(todayRow).toHaveTextContent('Currently closed')
    expect(todayRow).toHaveTextContent('9:00 am – 10:00 pm (scheduled)')
    // Other days keep their plain published window.
    expect(screen.getByText('Monday').closest('li')).toHaveTextContent('9:00 am – 10:00 pm')
    expect(screen.getByText('Monday').closest('li')).not.toHaveTextContent('Currently closed')
  })

  it('leaves outside-hours rows unchanged apart from the scheduled hint', () => {
    render(
      <RestaurantTimingControl
        restaurant={restaurant({
          is_accepting_orders: false,
          current_closes_at: null,
          next_opens_at: '09:00',
          next_opens_day: 3,
        })}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Outside opening hours/ }))
    const todayRow = screen.getByText('Today').closest('li')
    expect(todayRow).toHaveTextContent('9:00 am – 10:00 pm (scheduled)')
    expect(todayRow).not.toHaveTextContent('Currently closed')
  })

  it('explains an unpublished schedule inside the timings modal', () => {
    render(<RestaurantTimingControl restaurant={restaurant({ opening_hours: [] })} />)

    fireEvent.click(screen.getByRole('button', { name: /Open now.*View timings/ }))
    expect(screen.getByText(/has not published its weekly timings/)).toBeInTheDocument()
  })

  it('closes the dialog with its close control', () => {
    render(<RestaurantTimingControl restaurant={restaurant()} />)

    fireEvent.click(screen.getByRole('button', { name: /Open now.*View timings/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
