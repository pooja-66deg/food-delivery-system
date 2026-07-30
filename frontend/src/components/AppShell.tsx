import { Link, NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { useCart } from '../cart/CartContext'
import { useNotifications } from '../notifications/NotificationsContext'
import { BrandMark } from './BrandPanel'

export function AppShell() {
  const { user, logout } = useAuth()
  const { count } = useCart()
  const { unread } = useNotifications()
  const initials = user
    ? `${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}`.toUpperCase()
    : '?'

  const isCustomer = user?.role === 'customer'
  const isOwner = user?.role === 'restaurant' || user?.role === 'admin'
  const isDriver = user?.role === 'driver'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <BrandMark />
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/restaurants">Restaurants</NavLink>
          {isCustomer && (
            <NavLink to="/cart">
              <span>Cart</span>
              {count > 0 && <span className="nav-badge">{count}</span>}
            </NavLink>
          )}
          {isCustomer && <NavLink to="/orders">Orders</NavLink>}
          {isCustomer && <NavLink to="/payments">Payments</NavLink>}
          {isDriver && <NavLink to="/deliveries">Deliveries</NavLink>}
          {isOwner && <NavLink to="/restaurant/orders">Orders</NavLink>}
          {isOwner && <NavLink to="/manage">Manage</NavLink>}
          {user?.role === 'admin' && <NavLink to="/admin">Admin</NavLink>}
          <NavLink to="/notifications">Notifications</NavLink>
          <NavLink to="/account">Account</NavLink>
        </nav>

        <div className="sidebar-foot">
          <div className="avatar">{initials}</div>
          <div className="sidebar-user">
            <div className="sidebar-user-name">{user?.first_name} {user?.last_name}</div>
            <div className="muted" style={{ textTransform: 'capitalize' }}>{user?.role}</div>
          </div>
          <button className="sidebar-signout" onClick={logout} title="Sign out" aria-label="Sign out">
            ⏻
          </button>
        </div>
      </aside>

      <div className="app-content">
        <header className="topbar">
          <Link to="/notifications" className="bell" aria-label={`Notifications${unread ? ` (${unread} new)` : ''}`}>
            <span className="bell-icon" aria-hidden>🔔</span>
            {unread > 0 && <span className="bell-badge">{unread > 9 ? '9+' : unread}</span>}
          </Link>
        </header>
        <Outlet />
      </div>
    </div>
  )
}
