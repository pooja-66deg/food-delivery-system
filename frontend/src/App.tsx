import { Navigate, Route, Routes } from 'react-router-dom'

import { QueryProvider } from './providers/QueryProvider'
import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AccountPage } from './pages/account/AccountPage'
import { AdminLogin } from './pages/AdminLogin'
import { AdminPanel } from './pages/AdminPanel'
import { AdminPasswordReset } from './pages/AdminPasswordReset'
import { CartPage } from './pages/CartPage'
import { DriverPage } from './pages/DriverPage'
import { FavoritesPage } from './pages/FavoritesPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { LoginPage } from './pages/LoginPage'
import { NotificationsPage } from './pages/NotificationsPage'
import { OrderDetailPage } from './pages/OrderDetailPage'
import { OrdersPage } from './pages/OrdersPage'
import { OwnerPage } from './pages/owner/OwnerPage'
import { PaymentsPage } from './pages/PaymentsPage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { RestaurantOrdersPage } from './pages/RestaurantOrdersPage'
import { RestaurantsPage } from './pages/RestaurantsPage'
import { RestaurantDetailPage } from './pages/RestaurantDetailPage'
import { AdminAuthProvider, useAdminAuth } from './auth/AdminAuthContext'

function ProtectedAdminRoute({ children }: { children: React.ReactNode }) {
  const { adminToken } = useAdminAuth()
  if (!adminToken) {
    return <Navigate to="/admin/login" replace />
  }
  return <>{children}</>
}

export function App() {
  return (
    <QueryProvider>
      <AdminAuthProvider>
        <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Both public: a reset link is opened from a mail client that is not
          signed in, and the token in the URL is the credential. */}
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Admin routes - public login and password reset */}
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin/reset-password" element={<AdminPasswordReset />} />

      {/* Admin dashboard - protected routes */}
      <Route
        path="/admin/dashboard"
        element={
          <ProtectedAdminRoute>
            <AdminPanel />
          </ProtectedAdminRoute>
        }
      />
      <Route
        path="/admin/*"
        element={
          <ProtectedAdminRoute>
            <AdminPanel />
          </ProtectedAdminRoute>
        }
      />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/restaurants" element={<RestaurantsPage />} />
          <Route path="/restaurants/:id" element={<RestaurantDetailPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:id" element={<OrderDetailPage />} />
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/deliveries" element={<DriverPage />} />
          <Route path="/manage" element={<OwnerPage />} />
          <Route path="/restaurant/orders" element={<RestaurantOrdersPage />} />
          <Route path="/admin" element={<AdminPanel />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/restaurants" replace />} />
      <Route path="*" element={<Navigate to="/restaurants" replace />} />
    </Routes>
      </AdminAuthProvider>
    </QueryProvider>
  )
}
