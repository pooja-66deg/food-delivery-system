// Publishes the driver's position while they choose to share it.
//
// Sharing is opt-in and off by default: a page that tracked someone's position
// because they happened to have an active delivery would be tracking without
// consent. The choice is persisted so a mid-shift refresh does not silently
// stop sharing.
import { useCallback, useEffect, useRef, useState } from 'react'

import { deliveryApi } from '../api/delivery'

export type DriverLocationStatus =
  | 'off'
  | 'sharing'
  | 'denied'
  | 'unavailable'
  | 'unsupported'

export const SHARE_STORAGE_KEY = 'delivery.shareLocation'
// watchPosition fires far more often than the server needs. Post at most once
// per interval, and only when the driver has actually moved.
export const MIN_INTERVAL_MS = 10_000
export const MIN_DISTANCE_M = 25

const EARTH_RADIUS_M = 6_371_000

// 1 = PERMISSION_DENIED in the Geolocation API.
const PERMISSION_DENIED = 1

function metresBetween(
  a: { latitude: number; longitude: number },
  b: { latitude: number; longitude: number },
): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b.latitude - a.latitude)
  const dLon = toRad(b.longitude - a.longitude)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h))
}

export function useDriverLocation() {
  const supported = typeof navigator !== 'undefined' && !!navigator.geolocation
  const [sharing, setSharing] = useState(false)
  const [status, setStatus] = useState<DriverLocationStatus>(
    supported ? 'off' : 'unsupported',
  )
  const [lastUpdate, setLastUpdate] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const watchId = useRef<number | null>(null)
  const lastSent = useRef<{ at: number; latitude: number; longitude: number } | null>(null)

  const stopWatch = useCallback(() => {
    if (watchId.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId.current)
    }
    watchId.current = null
    lastSent.current = null
  }, [])

  const startWatch = useCallback(() => {
    if (!navigator.geolocation || watchId.current !== null) return
    watchId.current = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        const previous = lastSent.current
        const now = Date.now()
        if (
          previous &&
          now - previous.at < MIN_INTERVAL_MS &&
          metresBetween(previous, { latitude, longitude }) < MIN_DISTANCE_M
        ) {
          return
        }
        lastSent.current = { at: now, latitude, longitude }
        void deliveryApi
          .postLocation(latitude, longitude)
          .then(() => {
            setLastUpdate(now)
            setStatus('sharing')
            setError(null)
          })
          .catch(() => setError('Could not reach the server with your location.'))
      },
      (positionError) => {
        // Geolocation problems are carried by `status`, which the UI already
        // explains in words. `error` stays for failures the status cannot
        // express — a request that never reached the server — so the driver is
        // never told the same thing twice.
        setStatus(positionError.code === PERMISSION_DENIED ? 'denied' : 'unavailable')
      },
      { enableHighAccuracy: true, maximumAge: 5_000, timeout: 20_000 },
    )
  }, [])

  const enable = useCallback(async () => {
    setError(null)
    setSharing(true)
    setStatus('sharing')
    localStorage.setItem(SHARE_STORAGE_KEY, 'true')
    try {
      await deliveryApi.setOnline(true)
    } catch {
      setError('Could not mark you online.')
    }
    startWatch()
  }, [startWatch])

  const disable = useCallback(async () => {
    stopWatch()
    setSharing(false)
    setStatus(supported ? 'off' : 'unsupported')
    setLastUpdate(null)
    localStorage.setItem(SHARE_STORAGE_KEY, 'false')
    try {
      await deliveryApi.setOnline(false)
    } catch {
      setError('Could not mark you offline.')
    }
  }, [stopWatch, supported])

  // Resume sharing after a refresh if that is where the driver left it. Runs
  // once on mount deliberately: re-running would restart the watch on every
  // render.
  useEffect(() => {
    if (supported && localStorage.getItem(SHARE_STORAGE_KEY) === 'true') {
      void enable()
    }
    return stopWatch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { sharing, status, lastUpdate, error, enable, disable }
}
