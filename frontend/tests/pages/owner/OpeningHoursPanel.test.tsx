import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../src/api/client'
import { OpeningHoursPanel } from '../../../src/pages/owner/OpeningHoursPanel'
import type { OpeningHourDay } from '../../../src/api/restaurants'

const mocks = vi.hoisted(() => ({ update: vi.fn() }))

vi.mock('../../../src/api/restaurants', async () => {
  const actual = await vi.importActual<typeof import('../../../src/api/restaurants')>(
    '../../../src/api/restaurants',
  )
  return { ...actual, restaurantsApi: mocks }
})

const week: OpeningHourDay[] = Array.from({ length: 7 }, (_, day_of_week) => ({
  day_of_week,
  opens_at: '09:00',
  closes_at: '22:00',
  is_closed: false,
}))

function renderPanel(hours: OpeningHourDay[] = week, onSaved = () => {}) {
  return render(
    <OpeningHoursPanel restaurantId={7} hours={hours} onSaved={onSaved} />,
  )
}

describe('OpeningHoursPanel', () => {
  beforeEach(() => {
    mocks.update.mockReset()
    mocks.update.mockResolvedValue({})
  })

  it('saves the weekly schedule through restaurantsApi.update', async () => {
    const onSaved = vi.fn()
    renderPanel(week, onSaved)

    await userEvent.click(screen.getByRole('button', { name: 'Save hours' }))

    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ opening_hours: expect.any(Array) }),
      ),
    )
    const payload = mocks.update.mock.calls[0][1].opening_hours as OpeningHourDay[]
    expect(payload).toHaveLength(7)
    expect(payload[0]).toMatchObject({ day_of_week: 0, opens_at: '09:00', is_closed: false })
    expect(onSaved).toHaveBeenCalled()
  })

  it('clearing the schedule sends an empty list', async () => {
    renderPanel(week)

    await userEvent.click(screen.getByRole('button', { name: 'Clear schedule' }))

    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(7, { opening_hours: [] }),
    )
  })

  it('applies the first open day to the rest of the week', async () => {
    const week = [
      { day_of_week: 0, opens_at: '11:00', closes_at: '23:00', is_closed: false },
      ...Array.from({ length: 6 }, (_, i) => ({
        day_of_week: i + 1,
        opens_at: null,
        closes_at: null,
        is_closed: true,
      })),
    ]
    renderPanel(week)

    await userEvent.click(screen.getByRole('button', { name: 'Apply Monday to every day' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save hours' }))

    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    const payload = mocks.update.mock.calls[0][1].opening_hours as OpeningHourDay[]
    expect(payload).toHaveLength(7)
    for (const day of payload) {
      expect(day).toMatchObject({ opens_at: '11:00', closes_at: '23:00', is_closed: false })
    }
  })

  it('surfaces API errors without reporting success', async () => {
    const onSaved = vi.fn()
    mocks.update.mockRejectedValue(new ApiError('Invalid hours', 422))
    renderPanel(week, onSaved)

    await userEvent.click(screen.getByRole('button', { name: 'Save hours' }))

    expect(await screen.findByText('Invalid hours')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })
})
