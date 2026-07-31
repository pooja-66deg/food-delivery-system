import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'

import { restaurantsApi } from '../api/restaurants'
import type { RestaurantDetail } from '../api/restaurants'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useCart } from '../cart/CartContext'
import { Alert, Button } from '../components/ui'

export function RestaurantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const { add } = useCart()
  const [restaurant, setRestaurant] = useState<RestaurantDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [adding, setAdding] = useState<number | null>(null)

  const isCustomer = user?.role === 'customer'

  async function handleAdd(itemId: number, name: string) {
    setError(null)
    setNotice(null)
    setAdding(itemId)
    try {
      await add(itemId)
      setNotice(`Added ${name} to your cart.`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not add item.')
    } finally {
      setAdding(null)
    }
  }

  useEffect(() => {
    if (!id) return
    setError(null)
    restaurantsApi
      .get(Number(id))
      .then(setRestaurant)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load restaurant.'))
  }, [id])

  if (error) {
    return (
      <main className="app-main">
        <Link to="/restaurants" className="back-link">← Back to restaurants</Link>
        <Alert>{error}</Alert>
      </main>
    )
  }

  if (!restaurant) {
    return (
      <main className="app-main">
        <div className="empty">
          <span className="spin" aria-hidden /> Loading…
        </div>
      </main>
    )
  }

  return (
    <main className="app-main">
      <Link to="/restaurants" className="back-link">← Back to restaurants</Link>

      <motion.div
        className="rest-hero"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <div className="rest-hero-head">
          <h1>{restaurant.name}</h1>
          <span className={`badge ${restaurant.is_open ? 'badge-open' : 'badge-closed'}`}>
            {restaurant.is_open ? 'Open now' : 'Closed'}
          </span>
        </div>
        {restaurant.description && <p className="muted">{restaurant.description}</p>}
        <div className="rest-hero-meta">
          {restaurant.cuisine && <span className="chip">{restaurant.cuisine}</span>}
          <span className="chip">{restaurant.city}</span>
          <span className="chip">Min order ${Number(restaurant.min_order_amount).toFixed(2)}</span>
        </div>
      </motion.div>

      {notice && <Alert kind="ok">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}

      {restaurant.menu.length === 0 ? (
        <div className="empty">This kitchen hasn't published its menu yet.</div>
      ) : (
        restaurant.menu.map((category) => (
          <section key={category.id} className="menu-section">
            <h2>{category.name}</h2>
            <div className="menu-items">
              {category.items.map((item) => (
                <div key={item.id} className="menu-item">
                  <div>
                    <div className="menu-item-name">{item.name}</div>
                    {item.description && <div className="muted">{item.description}</div>}
                  </div>
                  <div className="menu-item-actions">
                    <div className="price">${Number(item.price).toFixed(2)}</div>
                    {isCustomer && (
                      <Button
                        variant="ghost"
                        loading={adding === item.id}
                        disabled={!item.is_available}
                        onClick={() => handleAdd(item.id, item.name)}
                      >
                        {item.is_available ? 'Add' : 'Unavailable'}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </main>
  )
}
