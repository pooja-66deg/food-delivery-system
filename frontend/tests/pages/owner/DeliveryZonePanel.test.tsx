import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../src/api/client'
import { DeliveryZonePanel } from '../../../src/pages/owner/DeliveryZonePanel'

const mocks = vi.hoisted(() => ({ update: vi.fn() }))

vi.mock('../../../src/api/restaurants', () => ({ restaurantsApi: mocks }))

function renderPanel(radiusKm: number | null, onSaved = () => {}) {
  return render(
    <DeliveryZonePanel restaurantId={7} radiusKm={radiusKm} onSaved={onSaved} />,
  )
}

const radiusInput = () => screen.getByLabelText('Delivery radius (km)')

describe('DeliveryZonePanel', () => {
  beforeEach(() => {
    mocks.update.mockReset()
    mocks.update.mockResolvedValue({})
  })

  it('shows the current radius', () => {
    renderPanel(8)

    expect(radiusInput()).toHaveValue(8)
  })

  it('leaves the field blank when no radius is set, so the default is not mistaken for a choice', () => {
    renderPanel(null)

    expect(radiusInput()).toHaveValue(null)
    expect(radiusInput()).toHaveAttribute('placeholder', 'Platform default')
  })

  it('saves a new radius and reports back', async () => {
    const onSaved = vi.fn()
    renderPanel(8, onSaved)

    await userEvent.clear(radiusInput())
    await userEvent.type(radiusInput(), '12.5')
    await userEvent.click(screen.getByRole('button', { name: 'Save radius' }))

    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(7, { delivery_radius_km: 12.5 }),
    )
    expect(onSaved).toHaveBeenCalled()
  })

  it('clearing the field sends null, returning the restaurant to the default', async () => {
    renderPanel(8)

    await userEvent.clear(radiusInput())
    await userEvent.click(screen.getByRole('button', { name: 'Save radius' }))

    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(7, { delivery_radius_km: null }),
    )
  })

  it('surfaces the API message on failure and does not report success', async () => {
    const onSaved = vi.fn()
    mocks.update.mockRejectedValue(new ApiError('Radius must be 100 km or less', 422))
    renderPanel(8, onSaved)

    await userEvent.click(screen.getByRole('button', { name: 'Save radius' }))

    expect(await screen.findByText('Radius must be 100 km or less')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('follows the selected restaurant instead of keeping the first one’s value', () => {
    const { rerender } = renderPanel(8)

    rerender(<DeliveryZonePanel restaurantId={9} radiusKm={3} onSaved={() => {}} />)

    expect(radiusInput()).toHaveValue(3)
  })
})
