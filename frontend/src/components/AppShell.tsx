import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { BrandMark } from './BrandPanel'

export function AppShell() {
  const { user, logout } = useAuth()
  const initials = user
    ? `${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}`.toUpperCase()
    : '?'

  return (
    <div className="app-shell">
      <nav className="app-nav">
        <div className="nav-links">
          <BrandMark />
          <NavLink to="/restaurants">Restaurants</NavLink>
          <NavLink to="/account">Account</NavLink>
        </div>
        <div className="nav-right">
          <span className="muted">Hi, {user?.first_name}</span>
          <div className="avatar" title={`${user?.first_name} ${user?.last_name}`}>
            {initials}
          </div>
          <button
            className="btn btn-ghost"
            style={{ padding: '0.5rem 0.9rem' }}
            onClick={logout}
          >
            Sign out
          </button>
        </div>
      </nav>
      <Outlet />
    </div>
  )
}
