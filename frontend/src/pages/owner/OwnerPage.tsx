import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { restaurantsApi } from '../../api/restaurants'
import type { Restaurant } from '../../api/restaurants'
import { useAuth } from '../../auth/AuthContext'
import { Alert, EmptyState } from '../../components/ui'
import { IncomingOrders } from './IncomingOrders'
import { MenuManager } from './MenuManager'
import { RestaurantForm } from './RestaurantForm'

export function OwnerPage() {
  const { user } = useAuth()
  const [mine, setMine] = useState<Restaurant[] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isOwner = user?.role === 'restaurant' || user?.role === 'admin'

  const loadMine = useCallback(async () => {
    if (!isOwner || !user) return
    try {
      // Browse is paged; an owner's own restaurants are few, so one large page
      // covers them. There is no "mine" endpoint to ask for directly.
      const all = (await restaurantsApi.list({ limit: 100 })).items
      const owned = all.filter((r) => r.owner_id === user.id || user.role === 'admin')
      setMine(owned)
      if (selectedId === null && owned.length > 0) setSelectedId(owned[0].id)
    } catch (e) {
      setError(errorMessage(e, 'Failed to load your restaurants.'))
    }
  }, [isOwner, user, selectedId])

  useEffect(() => {
    void loadMine()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOwner, user])

  if (!isOwner) {
    return (
      <main className="app-main">
        <h1>Manage</h1>
        <EmptyState>This area is for restaurant accounts.</EmptyState>
      </main>
    )
  }

  return (
    <main className="app-main">
      <h1>Manage your restaurants</h1>
      {error && <Alert>{error}</Alert>}

      <div className="owner-grid">
        {/* Left Panel: Restaurants */}
        <section className="owner-panel">
          <h2>Your restaurants</h2>
          {mine && mine.length > 0 ? (
            <div className="owner-rest-list">
              {mine.map((r) => (
                <button
                  key={r.id}
                  className="owner-rest-item"
                  data-active={r.id === selectedId}
                  onClick={() => setSelectedId(r.id)}
                >
                  <span>{r.name}</span>
                  <span className={`badge ${r.is_open ? 'badge-open' : 'badge-closed'}`}>
                    {r.is_open ? 'Open' : 'Closed'}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">No restaurants yet. Create your first one.</p>
          )}
          <RestaurantForm
            onCreated={async (r) => {
              await loadMine()
              setSelectedId(r.id)
            }}
          />
        </section>

        {/* Center Panel: Incoming Orders */}
        <section className="owner-panel">
          {selectedId === null ? (
            <EmptyState>Select a restaurant to view incoming orders.</EmptyState>
          ) : (
            <IncomingOrders restaurantId={selectedId} />
          )}
        </section>

        {/* Right Panel: Menu Manager */}
        <section className="owner-panel">
          {selectedId === null ? (
            <EmptyState>Select a restaurant to manage its menu.</EmptyState>
          ) : (
            <MenuManager restaurantId={selectedId} onChanged={loadMine} />
          )}
        </section>
      </div>
    </main>
  )
}
