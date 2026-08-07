import { useCallback, useEffect, useState } from 'react'

import { errorMessage } from '../../api/client'
import { ordersApi } from '../../api/orders'
import type { Order } from '../../api/orders'
import { restaurantsApi } from '../../api/restaurants'
import type { Restaurant, RestaurantDetail } from '../../api/restaurants'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Button, EmptyState, Loading, Modal } from '../../components/ui'
import { IncomingOrders } from './IncomingOrders'
import { RestaurantForm } from './RestaurantForm'
import { RestaurantWorkspace } from './RestaurantWorkspace'
import {
  categoryCount,
  dishCount,
  isLiveOrder,
  isSameDay,
  lowStockCount,
  orderValueToday,
  plural,
} from './ownerStats'

/** What the dashboard knows about one restaurant beyond its summary row. */
interface VenueStats {
  categories: number
  dishes: number
  lowStock: number
}

export function OwnerPage() {
  const { user } = useAuth()
  const [mine, setMine] = useState<Restaurant[] | null>(null)
  const [stats, setStats] = useState<Map<number, VenueStats>>(new Map())
  const [orders, setOrders] = useState<Order[]>([])
  const [error, setError] = useState<string | null>(null)
  // Which restaurant is opened for editing. null means the dashboard.
  const [openId, setOpenId] = useState<number | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  // Stamped once per load rather than read at render time, so every "3 min ago"
  // on the page is measured from the same instant.
  const [loadedAt, setLoadedAt] = useState(() => new Date())

  const isOwner = user?.role === 'restaurant' || user?.role === 'admin'

  const load = useCallback(async () => {
    if (!isOwner || !user) return
    try {
      // Browse is paged; an owner's own restaurants are few, so one large page
      // covers them. There is no "mine" endpoint to ask for directly.
      const all = (await restaurantsApi.list({ limit: 100 })).items
      const owned = all.filter((r) => r.owner_id === user.id || user.role === 'admin')
      setMine(owned)
      setLoadedAt(new Date())

      // Menus and orders are per restaurant, and the dashboard reports across all
      // of them. Fetched together so a slow kitchen does not hold up the rest,
      // and settled so one failure leaves the other rows populated.
      const [details, orderLists] = await Promise.all([
        Promise.allSettled(owned.map((r) => restaurantsApi.get(r.id))),
        Promise.allSettled(owned.map((r) => ordersApi.forRestaurant(r.id))),
      ])

      const nextStats = new Map<number, VenueStats>()
      details.forEach((result, i) => {
        if (result.status !== 'fulfilled') return
        const detail: RestaurantDetail = result.value
        nextStats.set(owned[i].id, {
          categories: categoryCount(detail),
          dishes: dishCount(detail),
          lowStock: lowStockCount(detail),
        })
      })
      setStats(nextStats)

      const merged = orderLists
        .filter((r): r is PromiseFulfilledResult<Order[]> => r.status === 'fulfilled')
        .flatMap((r) => r.value)
      setOrders(merged)
      setError(null)
    } catch (e) {
      setError(errorMessage(e, 'Failed to load your restaurants.'))
    }
  }, [isOwner, user])

  useEffect(() => {
    void load()
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

  const opened = mine?.find((r) => r.id === openId) ?? null

  // Opened venue takes over the page. A restaurant's menu wants the full width,
  // and keeping the dashboard above it just pushed the work off screen.
  if (opened) {
    const ordersToday = orders.filter(
      (o) => o.restaurant_id === opened.id && isSameDay(o.created_at, loadedAt),
    ).length
    return (
      <main className="app-main owner-page">
        <RestaurantWorkspace
          restaurantId={opened.id}
          ordersToday={ordersToday}
          onBack={() => setOpenId(null)}
          onChanged={() => void load()}
        />
      </main>
    )
  }

  const liveOrders = orders.filter(isLiveOrder)
  // Newest first: a kitchen reads the queue from the top.
  const queue = [...liveOrders].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )
  const names = new Map((mine ?? []).map((r) => [r.id, r.name]))

  return (
    <main className="app-main owner-page">
      <header className="owner-hero">
        <div>
          <p className="eyebrow">The pass</p>
          <h1>Restaurant manager</h1>
          <p className="owner-hero-lede">
            Watch orders land in real time, then open any venue to shape its categories, dishes,
            stock and pricing.
          </p>
        </div>
        {user?.role === 'admin' && (
          <Button onClick={() => setAddOpen(true)}>
            <span aria-hidden="true">+</span> New restaurant
          </Button>
        )}
      </header>

      {error && <Alert>{error}</Alert>}

      <div className="stat-tiles">
        <StatTile
          label="Restaurants"
          value={mine === null ? '—' : String(mine.length)}
          icon={<ChefHatIcon />}
        />
        <StatTile label="Live orders" value={String(liveOrders.length)} icon={<ClockIcon />} />
        <StatTile
          label="Order value today"
          value={`$${orderValueToday(orders, loadedAt).toFixed(2)}`}
          icon={<CutleryIcon />}
        />
      </div>

      <Modal
        open={addOpen}
        title="Add a restaurant"
        subtitle="You can upload a cover photo and build the menu once it exists."
        onClose={() => setAddOpen(false)}
      >
        <RestaurantForm
          onCreated={async (r) => {
            setAddOpen(false)
            await load()
            // Straight into the new kitchen — the next job is its menu.
            setOpenId(r.id)
          }}
        />
      </Modal>

      <div className="owner-columns">
        <section>
          <div className="column-head">
            <h2>Restaurants</h2>
            <p className="muted">Open a venue to manage its menu and stock.</p>
          </div>

          {mine === null ? (
            <Loading />
          ) : mine.length === 0 ? (
            <EmptyState>
              {user?.role === 'admin'
                ? 'No restaurants yet. Use “New restaurant” to create your first one.'
                : 'No restaurants assigned yet. Contact an administrator to add you to a restaurant.'}
            </EmptyState>
          ) : (
            <div className="venue-list">
              {mine.map((r) => {
                const stat = stats.get(r.id)
                return (
                  <button
                    key={r.id}
                    type="button"
                    className="venue-row"
                    onClick={() => setOpenId(r.id)}
                  >
                    <span className="venue-row-text">
                      <span className="venue-row-name">{r.name}</span>
                      <span className="muted venue-row-meta">
                        {r.cuisine ? `${r.cuisine} · ` : ''}
                        {/* Dashes until the per-restaurant menu fetch lands, rather
                            than "0 categories", which reads as an empty menu. */}
                        {stat
                          ? `${plural(stat.categories, 'category', 'categories')} · ${plural(stat.dishes, 'dish', 'dishes')}`
                          : r.city}
                      </span>
                    </span>
                    {!r.is_open && <span className="badge badge-closed">Closed</span>}
                    {stat && stat.lowStock > 0 && (
                      <span className="pill-warn">{plural(stat.lowStock, 'low stock', 'low stock')}</span>
                    )}
                    <span className="venue-row-go" aria-hidden="true">
                      →
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </section>

        <section>
          <div className="column-head">
            <h2>Incoming orders</h2>
            <p className="muted">Move each ticket along as the kitchen works.</p>
          </div>

          {mine === null ? (
            <Loading />
          ) : (
            <IncomingOrders
              orders={queue}
              names={names}
              now={loadedAt}
              onChanged={() => void load()}
            />
          )}
        </section>
      </div>
    </main>
  )
}

function StatTile({
  label,
  value,
  icon,
}: {
  label: string
  value: string
  icon: React.ReactNode
}) {
  return (
    <div className="stat-tile">
      <span className="stat-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="stat-text">
        <span className="stat-label">{label}</span>
        <span className="stat-value">{value}</span>
      </span>
    </div>
  )
}

/* Line icons drawn inline: three small marks are not worth an icon dependency,
   and as SVG they take the tile's accent colour in both themes. */
const STROKE = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

function ChefHatIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false">
      <path d="M7 14.5a3.6 3.6 0 1 1 1-7 4.3 4.3 0 0 1 8 0 3.6 3.6 0 1 1 1 7Z" {...STROKE} />
      <path d="M7.6 14.5v3.6h8.8v-3.6" {...STROKE} />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false">
      <circle cx="12" cy="12" r="8.4" {...STROKE} />
      <path d="M12 7.6V12l3 2" {...STROKE} />
    </svg>
  )
}

function CutleryIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false">
      <path d="M8 4v5.5a2 2 0 0 0 2 2v8.5" {...STROKE} />
      <path d="M12 4v5.5a2 2 0 0 1-2 2" {...STROKE} />
      <path d="M16.5 4c2 2.6 2 6 0 8.6V20" {...STROKE} />
    </svg>
  )
}
