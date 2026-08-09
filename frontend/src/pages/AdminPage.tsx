import { useCallback, useEffect, useState } from 'react'

import { adminApi } from '../api/admin'
import type { AdminOrder, AdminStats, AdminUser } from '../api/admin'
import { errorMessage } from '../api/client'
import { ordersApi } from '../api/orders'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, EmptyState } from '../components/ui'
import { RestaurantsPanel } from './admin/RestaurantsPanel'
import { statusLabel } from './orderStatus'

const TERMINAL = new Set(['COMPLETED', 'CANCELLED', 'REJECTED'])
type Section = 'overview' | 'restaurants' | 'orders' | 'users'

export function AdminPage() {
  const { user } = useAuth()
  const [section, setSection] = useState<Section>('overview')
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [orders, setOrders] = useState<AdminOrder[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const isAdmin = user?.role === 'admin'

  const load = useCallback(async () => {
    if (!isAdmin) return
    setError(null)
    try {
      const [s, u, o] = await Promise.all([adminApi.stats(), adminApi.users(), adminApi.orders()])
      setStats(s)
      setUsers(u)
      setOrders(o)
    } catch (e) {
      setError(errorMessage(e, 'Failed to load admin data.'))
    }
  }, [isAdmin])

  useEffect(() => {
    void load()
  }, [load])

  async function cancelOrder(id: number) {
    setError(null)
    setNotice(null)
    try {
      await ordersApi.setStatus(id, 'CANCELLED')
      setNotice(`Order #${id} cancelled.`)
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Could not cancel order.'))
    }
  }

  async function runSweep() {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      const { expired } = await adminApi.runTimeoutSweep()
      setNotice(`Timeout sweep ran — ${expired} order(s) expired.`)
      await load()
    } catch (e) {
      setError(errorMessage(e, 'Sweep failed.'))
    } finally {
      setBusy(false)
    }
  }

  if (!isAdmin) {
    return (
      <main className="app-main">
        <h1>Admin</h1>
        <EmptyState>This area is for admin accounts.</EmptyState>
      </main>
    )
  }

  const SECTIONS: { key: Section; label: string; count?: number }[] = [
    { key: 'overview', label: 'Overview' },
    // No count: the panel owns its own paging and filtering, and a stale
    // number in the sidebar would contradict the tab it points at.
    { key: 'restaurants', label: 'Manage restaurants' },
    { key: 'orders', label: 'Orders', count: orders.length },
    { key: 'users', label: 'Users', count: users.length },
  ]

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <span className="admin-brand-dot" aria-hidden />
          <span>Console</span>
        </div>
        <nav className="admin-nav">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              className="admin-nav-item"
              data-active={section === s.key}
              onClick={() => setSection(s.key)}
            >
              <span>{s.label}</span>
              {s.count !== undefined && <span className="side-badge">{s.count}</span>}
            </button>
          ))}
        </nav>
        <div className="admin-foot">
          <div className="admin-foot-name">{user?.first_name} {user?.last_name}</div>
          <div className="muted">Administrator</div>
        </div>
      </aside>

      <div className="admin-content">
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="ok">{notice}</Alert>}

        {section === 'restaurants' && <RestaurantsPanel />}

        {section === 'overview' && (
          <>
            <div className="admin-section-head">
              <h1>Overview</h1>
              <Button variant="ghost" loading={busy} onClick={runSweep}>
                Run timeout sweep
              </Button>
            </div>
            {stats && (
              <>
                <div className="stat-grid">
                  <StatTile label="Users" value={String(stats.users)} />
                  <StatTile label="Restaurants" value={String(stats.restaurants)} />
                  <StatTile label="Orders" value={String(stats.orders_total)} />
                  <StatTile label="GMV" value={`₹${Number(stats.gross_merchandise_value).toFixed(2)}`} accent />
                </div>
                <h2 className="admin-subhead">Orders by status</h2>
                {Object.keys(stats.orders_by_status).length === 0 ? (
                  <EmptyState>No orders placed yet.</EmptyState>
                ) : (
                  <div className="rest-hero-meta">
                    {Object.entries(stats.orders_by_status).map(([s, c]) => (
                      <span key={s} className="chip">{statusLabel(s)}: {c}</span>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}

        {section === 'orders' && (
          <>
            <div className="admin-section-head"><h1>Orders</h1></div>
            {orders.length === 0 ? (
              <EmptyState>No orders yet.</EmptyState>
            ) : (
              <div className="admin-table" role="table">
                <div className="admin-row admin-head-row" role="row">
                  <span>#</span><span>Status</span><span>Payment</span><span>Total</span><span>Placed</span><span></span>
                </div>
                {orders.map((o) => (
                  <div key={o.id} className="admin-row" role="row">
                    <span className="mono">#{o.id}</span>
                    <span><span className="chip">{statusLabel(o.status)}</span></span>
                    <span className="muted">{o.payment_status}</span>
                    <span className="price">₹{Number(o.total).toFixed(2)}</span>
                    <span className="muted">{new Date(o.created_at).toLocaleString()}</span>
                    <span>
                      {!TERMINAL.has(o.status) && (
                        <button className="link-danger" onClick={() => cancelOrder(o.id)}>Cancel</button>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {section === 'users' && (
          <>
            <div className="admin-section-head"><h1>Users</h1></div>
            <div className="admin-table" role="table">
              <div className="admin-row admin-users-row admin-head-row" role="row">
                <span>#</span><span>Email</span><span>Name</span><span>Role</span><span>Active</span>
              </div>
              {users.map((u) => (
                <div key={u.id} className="admin-row admin-users-row" role="row">
                  <span className="mono">#{u.id}</span>
                  <span>{u.email}</span>
                  <span>{u.first_name} {u.last_name}</span>
                  <span><span className={`role-tag role-${u.role}`}>{u.role}</span></span>
                  <span>{u.is_active ? 'Active' : 'Disabled'}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function StatTile({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="stat-tile" data-accent={accent}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
