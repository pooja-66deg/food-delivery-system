import { useState } from 'react'

import { favoritesApi } from '../api/favorites'

interface FavoriteButtonProps {
  restaurantId: number
  saved: boolean
  onToggled: (restaurantId: number, saved: boolean) => void
}

export function FavoriteButton({ restaurantId, saved, onToggled }: FavoriteButtonProps) {
  const [busy, setBusy] = useState(false)

  async function toggle(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (busy) return

    const next = !saved
    setBusy(true)
    onToggled(restaurantId, next)
    try {
      await (next ? favoritesApi.add(restaurantId) : favoritesApi.remove(restaurantId))
    } catch {
      onToggled(restaurantId, saved) // put it back
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      className={`fav-btn ${saved ? 'fav-on' : ''}`}
      aria-label={saved ? 'Remove from favourites' : 'Save to favourites'}
      aria-pressed={saved}
      onClick={(e) => void toggle(e)}
    >
     
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          d="M12 20.25 4.6 13.1a4.6 4.6 0 0 1 0-6.55 4.75 4.75 0 0 1 6.65 0l.75.73.75-.73a4.75 4.75 0 0 1 6.65 0 4.6 4.6 0 0 1 0 6.55Z"
          fill={saved ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  )
}
