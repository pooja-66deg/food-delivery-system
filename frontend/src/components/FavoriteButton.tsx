import { useState } from 'react'

import { favoritesApi } from '../api/favorites'

interface FavoriteButtonProps {
  restaurantId: number
  saved: boolean
  /** Told the new state so the owning page keeps one source of truth. */
  onToggled: (restaurantId: number, saved: boolean) => void
}

/**
 * The heart on a restaurant card.
 *
 * Optimistic: the heart flips immediately and reverts if the request fails,
 * because a save that takes a round trip to acknowledge feels broken. The button
 * also stops the click from reaching the card's surrounding link — a heart inside
 * an anchor would otherwise navigate away as well as save.
 */
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
      {saved ? '♥' : '♡'}
    </button>
  )
}
