import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Tracking } from '../../src/api/delivery'
import { DeliveryMap } from '../../src/components/DeliveryMap'

// The Maps SDK never loads in jsdom, so the loader is stubbed. What matters is
// that the component asks for it exactly when a key exists, and that it degrades
// to the text panel when the load fails.
const loader = vi.hoisted(() => ({ importLibrary: vi.fn(), setOptions: vi.fn() }))

vi.mock('@googlemaps/js-api-loader', () => ({
  importLibrary: loader.importLibrary,
  setOptions: loader.setOptions,
}))

// `new` on these returns the literal, so the stubs stand in for real instances.
const fitBounds = vi.fn()
const setPosition = vi.fn()
const mapsLibrary = { Map: vi.fn(() => ({ fitBounds })) }
const markerLibrary = { Marker: vi.fn(() => ({ setPosition, setMap: vi.fn() })) }

function stubSdk() {
  loader.importLibrary.mockReset().mockImplementation((name: string) =>
    Promise.resolve(name === 'marker' ? markerLibrary : mapsLibrary),
  )
}

const base: Tracking = {
  order_id: 1,
  status: 'PICKED_UP',
  driver_id: 3,
  driver: { latitude: 12.9716, longitude: 77.5946 },
  restaurant: { latitude: 12.9352, longitude: 77.6245 },
  destination: { latitude: 12.9, longitude: 77.6 },
  eta_minutes: 12,
  distance_km: 3.4,
  eta_source: 'estimate',
}

describe('DeliveryMap without a maps key', () => {
  // frontend/.env carries a real key and Vite exposes it to Vitest, so the
  // unkeyed path has to be stubbed explicitly — otherwise these tests would
  // silently exercise the map branch instead of the fallback.
  beforeEach(() => {
    vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', '')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('shows the ETA and distance as text', () => {
    render(<DeliveryMap tracking={base} />)

    expect(screen.getByText(/12 min/)).toBeInTheDocument()
    expect(screen.getByText(/3\.4 km/)).toBeInTheDocument()
  })

  it('marks a fallback ETA as estimated', () => {
    render(<DeliveryMap tracking={base} />)

    expect(screen.getByText(/estimated/i)).toBeInTheDocument()
  })

  it('does not hedge a Google ETA', () => {
    render(<DeliveryMap tracking={{ ...base, eta_source: 'google' }} />)

    expect(screen.queryByText(/estimated/i)).not.toBeInTheDocument()
    expect(screen.getByText(/12 min/)).toBeInTheDocument()
  })

  it('says it is still locating when the driver has no position', () => {
    render(
      <DeliveryMap
        tracking={{
          ...base,
          driver: null,
          eta_minutes: null,
          distance_km: null,
          eta_source: null,
        }}
      />,
    )

    expect(screen.getByText(/locating your driver/i)).toBeInTheDocument()
  })

  it('omits the ETA line when no ETA could be computed', () => {
    render(
      <DeliveryMap
        tracking={{ ...base, eta_minutes: null, distance_km: null, eta_source: null }}
      />,
    )

    expect(screen.queryByText(/min/)).not.toBeInTheDocument()
    expect(screen.getByText(/on the way to you/i)).toBeInTheDocument()
  })

  it('never renders the map container without a key', () => {
    render(<DeliveryMap tracking={base} />)

    expect(screen.queryByTestId('delivery-map')).not.toBeInTheDocument()
  })

  it('does not even try to load the SDK without a key', () => {
    render(<DeliveryMap tracking={base} />)

    expect(loader.importLibrary).not.toHaveBeenCalled()
  })
})

describe('DeliveryMap with a maps key', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOOGLE_MAPS_API_KEY', 'test-browser-key')
    stubSdk()
    fitBounds.mockClear()
    setPosition.mockClear()
    mapsLibrary.Map.mockClear()
    markerLibrary.Marker.mockClear()
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders the map container and keeps the ETA text', () => {
    render(<DeliveryMap tracking={base} />)

    expect(screen.getByTestId('delivery-map')).toBeInTheDocument()
    expect(screen.getByText(/12 min/)).toBeInTheDocument()
  })

  it('loads the SDK once a driver position exists', async () => {
    render(<DeliveryMap tracking={base} />)

    await waitFor(() => expect(loader.importLibrary).toHaveBeenCalled())
  })

  it('falls back to text when the driver position is unknown', () => {
    render(<DeliveryMap tracking={{ ...base, driver: null }} />)

    expect(screen.queryByTestId('delivery-map')).not.toBeInTheDocument()
    expect(screen.getByText(/locating your driver/i)).toBeInTheDocument()
  })

  it('keeps the ETA readable when the SDK fails to load', async () => {
    loader.importLibrary.mockReset().mockRejectedValue(new Error('blocked'))
    render(<DeliveryMap tracking={base} />)

    // The map canvas is gone, but the information is not.
    await waitFor(() => expect(screen.queryByTestId('delivery-map')).not.toBeInTheDocument())
    expect(screen.getByText(/12 min/)).toBeInTheDocument()
  })

  it('places one marker per known point and fits them all', async () => {
    render(<DeliveryMap tracking={base} />)

    await waitFor(() => expect(markerLibrary.Marker).toHaveBeenCalledTimes(3))
    expect(fitBounds).toHaveBeenCalledWith(
      { north: 12.9716, south: 12.9, east: 77.6245, west: 77.5946 },
      64,
    )
  })

  it('skips a point the server could not resolve', async () => {
    render(<DeliveryMap tracking={{ ...base, destination: null }} />)

    await waitFor(() => expect(markerLibrary.Marker).toHaveBeenCalledTimes(2))
  })

  it('moves the driver marker on a new poll instead of rebuilding the map', async () => {
    const { rerender } = render(<DeliveryMap tracking={base} />)
    await waitFor(() => expect(markerLibrary.Marker).toHaveBeenCalledTimes(3))

    rerender(
      <DeliveryMap
        tracking={{ ...base, driver: { latitude: 12.98, longitude: 77.61 }, eta_minutes: 9 }}
      />,
    )

    await waitFor(() =>
      expect(setPosition).toHaveBeenCalledWith({ lat: 12.98, lng: 77.61 }),
    )
    // Still three markers and one map: the poll mutates, it does not re-create.
    expect(markerLibrary.Marker).toHaveBeenCalledTimes(3)
    expect(mapsLibrary.Map).toHaveBeenCalledTimes(1)
  })
})
