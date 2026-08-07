import { importLibrary, setOptions } from '@googlemaps/js-api-loader'
import { useEffect, useRef, useState } from 'react'

import type { Coordinate, Tracking } from '../api/delivery'

export function mapsKey(): string | undefined {
  const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
  return key ? key : undefined
}

// SVG icons for markers
const BIKE_ICON = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSI4IiBjeT0iMjQiIHI9IjYiIGZpbGw9IiNmZjY2MzMiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIyIi8+PHBhdGggZD0iTTEyIDEwTDIwIDEwTDIwIDIySDEyVjEwWiIgZmlsbD0iI2ZmNjYzMyIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48Y2lyY2xlIGN4PSIyNCIgY3k9IjI0IiByPSI2IiBmaWxsPSIjZmY2NjMzIiBzdHJva2U9IiNmZmYiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg=='
const RESTAURANT_ICON = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB4PSI4IiB5PSI4IiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHJ4PSIyIiBmaWxsPSIjZmY0NDAwIiBzdHJva2U9IiNmZmYiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg=='
const HOME_ICON = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTYgNEw0IDE0VjI4SDEyVjIwSDIwVjI4SDI4VjE0TDE2IDRaIiBmaWxsPSIjNDRBQTk5IiBzdHJva2U9IiNmZmYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPjwvc3ZnPg=='

export function etaLabel(tracking: Tracking): string | null {
  if (tracking.eta_minutes === null) return null
  const distance =
    tracking.distance_km !== null ? ` · ${tracking.distance_km.toFixed(1)} km away` : ''
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

function useTrackingMap(apiKey: string | undefined, tracking: Tracking) {
  const container = useRef<HTMLDivElement | null>(null)
  const map = useRef<any>(null)
  const markerCtor = useRef<any>(null)
  const markers = useRef<Map<string, any>>(new Map())
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  const active = Boolean(apiKey) && tracking.driver !== null

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
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
    }
  }, [apiKey, active])

  useEffect(() => {
    const Marker = markerCtor.current
    if (!map.current || !Marker) return

    const known = points(tracking)
    if (known.length === 0) return

    for (const { key, point, title } of known) {
      const position = latLng(point)
      const existing = markers.current.get(key)

      // Choose icon based on marker type
      let iconUrl: string | undefined
      if (key === 'driver') {
        iconUrl = BIKE_ICON
      } else if (key === 'restaurant') {
        iconUrl = RESTAURANT_ICON
      } else if (key === 'destination') {
        iconUrl = HOME_ICON
      }

      const iconConfig = iconUrl ? {
        url: iconUrl,
        scaledSize: { width: 32, height: 32 },
      } : undefined

      if (existing) {
        existing.setPosition(position)
      } else {
        markers.current.set(key, new Marker({
          map: map.current,
          position,
          title,
          icon: iconConfig,
        }))
      }
    }

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
