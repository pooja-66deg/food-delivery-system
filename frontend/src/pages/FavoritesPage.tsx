import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

import { errorMessage } from '../api/client'
import { favoritesApi } from '../api/favorites'
import type { Restaurant } from '../api/restaurants'
import { FavoriteButton } from '../components/FavoriteButton'
import { Alert, EmptyState, Loading, Thumb } from '../components/ui'
import { RatingStars } from '../reviews/RatingStars'
import { reviewCountLabel } from '../reviews/RatingSummary'

const BAND_LABELS: Record<number, string> = { 1: '$', 2: '$$', 3: '$$$' }

/**
 * The customer's saved restaurants.
 *
 * Un-hearting removes the card immediately rather than leaving it in a list
 * titled "favourites" — this page is the set, so leaving it would contradict
 * itself.
 */
export function FavoritesPage() {
  const [items, setItems] = useState<Restaurant[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        setItems(await favoritesApi.list())
      } catch (e) {
        setError(errorMessage(e, 'Could not load your saved restaurants.'))
        setItems([])
      }
    })()
  }, [])

  const onToggled = (restaurantId: number, saved: boolean) => {
    if (!saved) setItems((current) => (current ?? []).filter((r) => r.id !== restaurantId))
  }

  return (
    <main className="app-main">
      <motion.div
        className="page-head"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <span className="chip chip-accent">Saved</span>
        <h1 style={{ marginTop: '0.6rem' }}>Your favourites</h1>
        <p>Kitchens you have saved, most recent first.</p>
      </motion.div>

      {error && <Alert>{error}</Alert>}

      {items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState>
          Nothing saved yet.{' '}
          <Link to="/restaurants" className="back-link">Find a kitchen →</Link>
        </EmptyState>
      ) : (
        <div className="rest-grid">
          {items.map((r) => (
            <div key={r.id}>
              <Link to={`/restaurants/${r.id}`} className="rest-card">
                <Thumb url={r.image_url} alt={`${r.name} cover`} variant="cover" />
                <div className="rest-card-top">
                  <span className={`badge ${r.is_open ? 'badge-open' : 'badge-closed'}`}>
                    {r.is_open ? 'Open' : 'Closed'}
                  </span>
                  {r.cuisine && <span className="chip">{r.cuisine}</span>}
                  <FavoriteButton restaurantId={r.id} saved onToggled={onToggled} />
                </div>
                <h3>{r.name}</h3>
                <p className="muted">{r.description ?? 'Freshly prepared meals.'}</p>
                <div className="rest-card-rating">
                  {r.rating_average === null ? (
                    <span className="chip">New</span>
                  ) : (
                    <>
                      <RatingStars value={r.rating_average} />
                      <span className="muted">
                        {r.rating_average} · {reviewCountLabel(r.review_count)}
                      </span>
                    </>
                  )}
                </div>
                <div className="rest-card-foot">
                  <span>
                    {r.city}
                    {r.price_band ? ` · ${BAND_LABELS[r.price_band]}` : ''}
                  </span>
                  <span>Min ₹{Number(r.min_order_amount).toFixed(2)}</span>
                </div>
              </Link>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
