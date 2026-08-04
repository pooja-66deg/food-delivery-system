import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useDriverLocation } from '../../src/lib/useDriverLocation'

const mocks = vi.hoisted(() => ({
  setOnline: vi.fn(),
  postLocation: vi.fn(),
}))

vi.mock('../../src/api/delivery', () => ({ deliveryApi: mocks }))

type WatchSuccess = (position: { coords: { latitude: number; longitude: number } }) => void
type WatchFailure = (error: { code: number; message: string }) => void

let onPosition: WatchSuccess | null = null
let onFailure: WatchFailure | null = null

function mockGeolocation() {
  onPosition = null
  onFailure = null
  const geolocation = {
    watchPosition: vi.fn((success: WatchSuccess, failure: WatchFailure) => {
      onPosition = success
      onFailure = failure
      return 1
    }),
    clearWatch: vi.fn(),
  }
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: geolocation,
    configurable: true,
    writable: true,
  })
  return geolocation
}

function emit(latitude: number, longitude: number) {
  act(() => {
    onPosition?.({ coords: { latitude, longitude } })
  })
}

beforeEach(() => {
  localStorage.clear()
  mocks.setOnline.mockReset().mockResolvedValue({ driver_id: 1, online: true })
  mocks.postLocation.mockReset().mockResolvedValue({ driver_id: 1, latitude: 0, longitude: 0 })
})

describe('useDriverLocation', () => {
  it('starts off and posts nothing', () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())

    expect(result.current.sharing).toBe(false)
    expect(result.current.status).toBe('off')
    expect(mocks.postLocation).not.toHaveBeenCalled()
    expect(mocks.setOnline).not.toHaveBeenCalled()
  })

  it('going online marks the driver available then posts the position', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())

    await act(async () => {
      await result.current.enable()
    })
    expect(mocks.setOnline).toHaveBeenCalledWith(true)

    emit(12.9716, 77.5946)
    await waitFor(() => expect(mocks.postLocation).toHaveBeenCalledWith(12.9716, 77.5946))
    expect(result.current.status).toBe('sharing')
  })

  it('suppresses an update that has barely moved', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => {
      await result.current.enable()
    })

    emit(12.9716, 77.5946)
    await waitFor(() => expect(mocks.postLocation).toHaveBeenCalledTimes(1))

    emit(12.97161, 77.59461) // ~1.5 m later, inside both thresholds
    expect(mocks.postLocation).toHaveBeenCalledTimes(1)
  })

  it('posts again when the driver has genuinely moved', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => {
      await result.current.enable()
    })

    emit(12.9716, 77.5946)
    await waitFor(() => expect(mocks.postLocation).toHaveBeenCalledTimes(1))

    emit(12.9816, 77.6046) // well over 25 m
    await waitFor(() => expect(mocks.postLocation).toHaveBeenCalledTimes(2))
  })

  it('reports a denied permission and posts nothing', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => {
      await result.current.enable()
    })

    act(() => {
      onFailure?.({ code: 1, message: 'denied' })
    })

    await waitFor(() => expect(result.current.status).toBe('denied'))
    // The wording lives with the UI that renders it; the hook reports state, and
    // `error` stays null so the driver is not told the same thing twice.
    expect(result.current.error).toBeNull()
    expect(mocks.postLocation).not.toHaveBeenCalled()
  })

  it('distinguishes an unavailable position from a denied one', async () => {
    mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => {
      await result.current.enable()
    })

    act(() => {
      onFailure?.({ code: 2, message: 'position unavailable' })
    })

    await waitFor(() => expect(result.current.status).toBe('unavailable'))
  })

  it('going offline clears the watch and marks the driver unavailable', async () => {
    const geolocation = mockGeolocation()
    const { result } = renderHook(() => useDriverLocation())
    await act(async () => {
      await result.current.enable()
    })
    await act(async () => {
      await result.current.disable()
    })

    expect(mocks.setOnline).toHaveBeenLastCalledWith(false)
    expect(geolocation.clearWatch).toHaveBeenCalled()
    expect(result.current.status).toBe('off')
    expect(result.current.sharing).toBe(false)
  })

  it('resumes sharing after a refresh if that is where the driver left it', async () => {
    mockGeolocation()
    localStorage.setItem('delivery.shareLocation', 'true')

    const { result } = renderHook(() => useDriverLocation())

    await waitFor(() => expect(mocks.setOnline).toHaveBeenCalledWith(true))
    expect(result.current.sharing).toBe(true)
  })

  it('reports unsupported when the browser has no geolocation', () => {
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: undefined,
      configurable: true,
      writable: true,
    })

    const { result } = renderHook(() => useDriverLocation())
    expect(result.current.status).toBe('unsupported')
    expect(mocks.setOnline).not.toHaveBeenCalled()
  })
})
