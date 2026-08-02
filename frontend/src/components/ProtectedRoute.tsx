import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    // Not <Loading />: that renders the inline `.empty` placeholder used inside
    // lists, whereas this is a full-viewport gate. Same role="status" contract,
    // different layout.
    return (
      <div className="full-center" role="status">
        <span className="spin" aria-hidden />
        <span>Loading your account…</span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
