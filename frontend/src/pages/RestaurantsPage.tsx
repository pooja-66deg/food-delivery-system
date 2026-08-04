import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

import { restaurantsApi } from '../api/restaurants'
import type { CuisineCount, Restaurant, RestaurantSuggestion } from '../api/restaurants'
import { errorMessage } from '../api/client'
import { Alert, Button, EmptyState, Loading, Thumb } from '../components/ui'
import { PopularCuisines } from '../components/PopularCuisines'
import { SearchSuggest } from '../components/SearchSuggest'
import { RatingStars } from '../reviews/RatingStars'
import { reviewCountLabel } from '../reviews/RatingSummary'

export function RestaurantsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Restaurant[] | null>(null)
  const [cuisines, setCuisines] = useState<CuisineCount[]>([])
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [city, setCity] = useState('')

  // Overrides let a cuisine chip search immediately with its own term instead
  // of racing the `search` state update.
  const load = async (overrides?: { search?: string; city?: string }) => {
    const term = overrides?.search ?? search
    const place = overrides?.city ?? city
    setError(null)
    try {
      setItems(await restaurantsApi.list({ search: term || undefined, city: place || undefined }))
    } catch (e) {
      setError(errorMessage(e, 'Failed to load restaurants.'))
      setItems([])
    }
  }

  useEffect(() => {
    void load()
    // Discovery chips are a nice-to-have: a failure here must not take the
    // page down with it.
    void restaurantsApi
      .popularCuisines()
      .then(setCuisines)
      .catch(() => setCuisines([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchSuggestions = useCallback((q: string) => restaurantsApi.suggest(q), [])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void load()
  }

  // Picking a named restaurant means "take me there", not "filter by this text".
  const onSuggestionChosen = (s: RestaurantSuggestion) => navigate(`/restaurants/${s.id}`)

  const onCuisinePicked = (cuisine: string) => {
    setSearch(cuisine)
    void load({ search: cuisine })
  }

  return (
    <main className="app-main">
      <motion.div
        className="page-head"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <span className="chip chip-accent">Discover</span>
        <h1 style={{ marginTop: '0.6rem' }}>Kitchens near you</h1>
        <p>Search by name or filter by city.</p>
      </motion.div>

      <form className="toolbar" onSubmit={onSubmit}>
        <SearchSuggest
          value={search}
          onChange={setSearch}
          onSelect={onSuggestionChosen}
          fetchSuggestions={fetchSuggestions}
        />
        <input
          className="input"
          placeholder="City"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          style={{ maxWidth: 200 }}
        />
        <Button type="submit">Search</Button>
      </form>

      <PopularCuisines cuisines={cuisines} onPick={onCuisinePicked} />

      {error && <Alert>{error}</Alert>}

      {items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState>No restaurants found. Try a different search.</EmptyState>
      ) : (
        <div className="rest-grid">
          {items.map((r, i) => (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: Math.min(i * 0.04, 0.3) }}
            >
              <Link to={`/restaurants/${r.id}`} className="rest-card">
                <Thumb url={r.image_url} alt={`${r.name} cover`} variant="cover" />
                <div className="rest-card-top">
                  <span className={`badge ${r.is_open ? 'badge-open' : 'badge-closed'}`}>
                    {r.is_open ? 'Open' : 'Closed'}
                  </span>
                  {r.cuisine && <span className="chip">{r.cuisine}</span>}
                </div>
                <h3>{r.name}</h3>
                <p className="muted">{r.description ?? 'Freshly prepared meals.'}</p>
                <div className="rest-card-rating">
                  {r.rating_average === null ? (
                    // Not "0 stars" — an unrated kitchen is new, not bad.
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
                  <span>{r.city}</span>
                  <span>Min ${Number(r.min_order_amount).toFixed(2)}</span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </main>
  )
}
