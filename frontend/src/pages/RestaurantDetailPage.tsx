import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'

import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useCart } from '../cart/CartContext'
import { RestaurantTimingControl } from '../components/RestaurantHours'
import { Alert, Button, EmptyState, Loading, Thumb } from '../components/ui'
import { useRestaurantDetail } from '../hooks/queries/useRestaurantQueries'
import { RatingStars } from '../reviews/RatingStars'
import { RatingSummary } from '../reviews/RatingSummary'
import { ReviewsSection } from '../reviews/ReviewsSection'

/** Show the count only when it is low enough to influence a decision. */
const LOW_STOCK_AT = 5

export function RestaurantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const { add } = useCart()
  const {
    data: restaurant,
    isLoading,
    error: loadError,
  } = useRestaurantDetail(id ? Number(id) : undefined)
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
      setError(errorMessage(e, 'Could not add item.'))
    } finally {
      setAdding(null)
    }
  }

  if (loadError) {
    return (
      <main className="app-main">
        <Link to="/restaurants" className="back-link">← Back to restaurants</Link>
        <Alert>{errorMessage(loadError, 'Failed to load restaurant.')}</Alert>
      </main>
    )
  }

  if (isLoading || !restaurant) {
    return (
      <main className="app-main">
        <Loading />
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
          <Thumb url={restaurant.image_url} alt={`${restaurant.name} cover`} variant="cover" />
          <h1>{restaurant.name}</h1>
        </div>
        {restaurant.description && <p className="muted">{restaurant.description}</p>}
        <RestaurantTimingControl restaurant={restaurant} />
        <div className="rest-hero-meta">
          {restaurant.rating_average !== null && (
            <span className="chip">
              <RatingStars value={restaurant.rating_average} /> {restaurant.rating_average}
            </span>
          )}
          {restaurant.cuisine && <span className="chip">{restaurant.cuisine}</span>}
          <span className="chip">{restaurant.city}</span>
          <span className="chip">Min order ₹{Number(restaurant.min_order_amount).toFixed(2)}</span>
        </div>
      </motion.div>

      {notice && <Alert kind="ok">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}

      {restaurant.menu.length === 0 ? (
        <EmptyState>This kitchen hasn't published its menu yet.</EmptyState>
      ) : (
        restaurant.menu.map((category) => (
          <section key={category.id} className="menu-section">
            <h2>{category.name}</h2>
            <div className="menu-items">
              {category.items.map((item) => (
                <div key={item.id} className="menu-item">
                  <div className="menu-item-lead">
                    <Thumb url={item.image_url} alt={item.name} />
                    <div>
                      <div className="menu-item-name">
                        {item.name}
                        {!item.in_stock && <span className="badge badge-closed">Out of stock</span>}
                      </div>
                      {item.description && <div className="muted">{item.description}</div>}
                      {item.in_stock &&
                        item.stock_quantity !== null &&
                        item.stock_quantity <= LOW_STOCK_AT && (
                          <div className="muted">Only {item.stock_quantity} left</div>
                        )}
                    </div>
                  </div>
                  <div className="menu-item-actions">
                    <div className="price">₹{Number(item.price).toFixed(2)}</div>
                    {isCustomer && (
                      <Button
                        variant="ghost"
                        loading={adding === item.id}
                        disabled={!item.in_stock}
                        onClick={() => handleAdd(item.id, item.name)}
                      >
                        {item.in_stock ? 'Add' : 'Unavailable'}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}

      <section className="menu-section">
        <h2>Ratings</h2>
        <RatingSummary
          average={restaurant.rating_average}
          count={restaurant.review_count}
          breakdown={restaurant.rating_breakdown}
        />
      </section>

      <ReviewsSection restaurantId={restaurant.id} ownerId={restaurant.owner_id} />
    </main>
  )
}
