import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DriverPage } from '../../src/pages/DriverPage'
import { NotificationsProvider } from '../../src/notifications/NotificationsContext'

const mocks = vi.hoisted(() => ({
  assignments: vi.fn(),
  accept: vi.fn(),
  reject: vi.fn(),
  pickup: vi.fn(),
  deliver: vi.fn(),
  setOnline: vi.fn(),
  postLocation: vi.fn(),
}))

vi.mock('../../src/api/delivery', () => ({ deliveryApi: mocks }))
vi.mock('../../src/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 3, role: 'driver' } }),
}))

function assignment(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    order_id: 77,
    driver_id: 3,
    status: 'ACCEPTED',
    assigned_at: null,
    picked_up_at: null,
    delivered_at: null,
    restaurant: { latitude: 12.9352, longitude: 77.6245 },
    destination: { latitude: 12.9, longitude: 77.6 },
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
  mocks.assignments.mockReset().mockResolvedValue([assignment()])
  mocks.setOnline.mockReset().mockResolvedValue({ driver_id: 3, online: true })
  mocks.postLocation.mockReset().mockResolvedValue({ driver_id: 3, latitude: 0, longitude: 0 })
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: { watchPosition: vi.fn(() => 1), clearWatch: vi.fn() },
    configurable: true,
    writable: true,
  })
})

describe('DriverPage location sharing', () => {
  it('offers sharing as off by default', async () => {
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )

    const toggle = await screen.findByRole('switch', { name: /share my location/i })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(mocks.setOnline).not.toHaveBeenCalled()
  })

  it('turning it on marks the driver online', async () => {
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )

    await userEvent.click(await screen.findByRole('switch', { name: /share my location/i }))

    await waitFor(() => expect(mocks.setOnline).toHaveBeenCalledWith(true))
    expect(await screen.findByText(/sharing your location/i)).toBeInTheDocument()
  })

  it('turning it off marks the driver unavailable', async () => {
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )
    const toggle = await screen.findByRole('switch', { name: /share my location/i })

    await userEvent.click(toggle)
    await waitFor(() => expect(mocks.setOnline).toHaveBeenCalledWith(true))
    await userEvent.click(toggle)

    await waitFor(() => expect(mocks.setOnline).toHaveBeenLastCalledWith(false))
  })

  it('explains a blocked permission instead of failing silently', async () => {
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: {
        watchPosition: vi.fn((_ok, onError) => {
          onError({ code: 1, message: 'denied' })
          return 1
        }),
        clearWatch: vi.fn(),
      },
      configurable: true,
      writable: true,
    })
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )

    await userEvent.click(await screen.findByRole('switch', { name: /share my location/i }))

    expect(await screen.findByText(/location permission is blocked/i)).toBeInTheDocument()
  })
})

describe('DriverPage next-stop navigation', () => {
  it('points at the restaurant before pickup', async () => {
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )

    const link = await screen.findByRole('link', { name: /navigate/i })
    expect(link.getAttribute('href')).toContain('destination=12.9352,77.6245')
  })

  it('points at the customer once the order is picked up', async () => {
    mocks.assignments.mockResolvedValue([assignment({ status: 'PICKED_UP' })])
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )

    const link = await screen.findByRole('link', { name: /navigate/i })
    expect(link.getAttribute('href')).toContain('destination=12.9,77.6')
  })

  it('omits the link when no coordinate is known', async () => {
    mocks.assignments.mockResolvedValue([
      assignment({ restaurant: null, destination: null }),
    ])
    render(
      <NotificationsProvider>
        <DriverPage />
      </NotificationsProvider>,
    )

    await screen.findByText(/order #77/i)
    expect(screen.queryByRole('link', { name: /navigate/i })).not.toBeInTheDocument()
  })
})
