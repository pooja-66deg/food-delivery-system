// Live delivery tracking. Renders a Google map when a browser key is configured
// and a text panel when it is not — the ETA comes from the server either way, so
// the information is identical and only the presentation drops.
import { importLibrary, setOptions } from '@googlemaps/js-api-loader'
import { useEffect, useRef, useState } from 'react'

import type { Coordinate, Tracking } from '../api/delivery'

export function mapsKey(): string | undefined {
  const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
  return key ? key : undefined
}

export function etaLabel(tracking: Tracking): string | null {
  if (tracking.eta_minutes === null) return null
  const distance =
    tracking.distance_km !== null ? ` · ${tracking.distance_km.toFixed(1)} km away` : ''
  // "estimated" is the honest word for the haversine fallback. A Google ETA
  // accounts for traffic and does not need the hedge.
  const hedge = tracking.eta_source === 'estimate' ? ' (estimated)' : ''
  return `Arriving in ~${tracking.eta_minutes} min${distance}${hedge}`
}

const latLng = (p: Coordinate) => ({ lat: p.latitude, lng: p.longitude })

/** Every known point on the journey, in draw order. */
function points(tracking: Tracking): { key: string; point: Coordinate; title: string }[] {
  return [
    { key: 'driver', point: tracking.driver, title: 'Your driver' },
    { key: 'restaurant', point: tracking.restaurant, title: 'Restaurant' },
    { key: 'destination', point: tracking.destination, title: 'Your address' },
  ].filter((m): m is { key: string; point: Coordinate; title: string } => m.point !== null)
}

/**
 * The Maps SDK is imperative and long-lived, so it is created once per mount and
 * then *mutated* as tracking updates. Re-creating the map on every 5-second poll
 * would flicker and re-fit the viewport under the user.
 */
function useTrackingMap(apiKey: string | undefined, tracking: Tracking) {
  const container = useRef<HTMLDivElement | null>(null)
  const map = useRef<google.maps.Map | null>(null)
  const markerCtor = useRef<typeof google.maps.Marker | null>(null)
  const markers = useRef<Map<string, google.maps.Marker>>(new Map())
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  const active = Boolean(apiKey) && tracking.driver !== null

  // Load the SDK and create the map. Runs once per mount.
  useEffect(() => {
    if (!active || !apiKey) return
    let cancelled = false

    setOptions({ key: apiKey, v: 'weekly' })
    Promise.all([importLibrary('maps'), importLibrary('marker')])
      .then(([maps, marker]) => {
        if (cancelled || !container.current || map.current) return
        map.current = new maps.Map(container.current, {
          center: latLng(tracking.driver!),
          zoom: 14,
          disableDefaultUI: true,
          gestureHandling: 'greedy',
        })
        markerCtor.current = marker.Marker
        setReady(true)
      })
      .catch(() => {
        // A blocked key, an offline browser, or a referrer rejection all land
        // here. The text panel still carries the ETA, so degrade rather than
        // leave an empty grey box.
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
    }
    // apiKey and `active` decide whether a map exists at all; tracking changes
    // are handled by the mutation effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, active])

  // Move the markers and re-fit the viewport as new positions arrive.
  useEffect(() => {
    const Marker = markerCtor.current
    if (!map.current || !Marker) return

    const known = points(tracking)
    if (known.length === 0) return

    for (const { key, point, title } of known) {
      const position = latLng(point)
      const existing = markers.current.get(key)
      if (existing) {
        existing.setPosition(position)
      } else {
        markers.current.set(key, new Marker({ map: map.current, position, title }))
      }
    }

    // A bounds *literal* rather than new google.maps.LatLngBounds(): no extra
    // global to reach for, and it is trivially inspectable.
    const lats = known.map((m) => m.point.latitude)
    const lngs = known.map((m) => m.point.longitude)
    map.current.fitBounds(
      {
        north: Math.max(...lats),
        south: Math.min(...lats),
        east: Math.max(...lngs),
        west: Math.min(...lngs),
      },
      64,
    )
  }, [tracking, ready])

  // Drop the markers when the card unmounts; the map goes with its container.
  useEffect(
    () => () => {
      markers.current.forEach((marker) => marker.setMap(null))
      markers.current.clear()
    },
    [],
  )

  return { container, show: active && !failed }
}

export function DeliveryMap({ tracking }: { tracking: Tracking }) {
  const eta = etaLabel(tracking)
  const { container, show } = useTrackingMap(mapsKey(), tracking)

  return (
    <div className="track-card">
      {show && <div className="track-map" data-testid="delivery-map" ref={container} />}
      <div className="track-line">
        <span className="track-pulse" aria-hidden />
        <div className="track-body">
          <div className="menu-item-name">Out for delivery</div>
          {tracking.driver ? (
            <div className="muted">{eta ?? 'On the way to you'}</div>
          ) : (
            <div className="muted">Locating your driver…</div>
          )}
        </div>
      </div>
    </div>
  )
}
