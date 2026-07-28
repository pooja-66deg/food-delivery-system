import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

import { restaurantsApi } from '../api/restaurants'
import type { Restaurant } from '../api/restaurants'
import { ApiError } from '../api/client'
import { Alert, Button } from '../components/ui'

export function RestaurantsPage() {
  const [items, setItems] = useState<Restaurant[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [city, setCity] = useState('')

  const load = async () => {
    setError(null)
    try {
      setItems(await restaurantsApi.list({ search: search || undefined, city: city || undefined }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load restaurants.')
      setItems([])
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void load()
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
        <input
          className="input"
          placeholder="Search restaurants…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
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

      {error && <Alert>{error}</Alert>}

      {items === null ? (
        <div className="empty">
          <span className="spin" aria-hidden /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div className="empty">No restaurants found. Try a different search.</div>
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
                <div className="rest-card-top">
                  <span className={`badge ${r.is_open ? 'badge-open' : 'badge-closed'}`}>
                    {r.is_open ? 'Open' : 'Closed'}
                  </span>
                  {r.cuisine && <span className="chip">{r.cuisine}</span>}
                </div>
                <h3>{r.name}</h3>
                <p className="muted">{r.description ?? 'Freshly prepared meals.'}</p>
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
