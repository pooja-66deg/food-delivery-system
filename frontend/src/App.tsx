import { Navigate, Route, Routes } from 'react-router-dom'

import { QueryProvider } from './providers/QueryProvider'
import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AccountPage } from './pages/account/AccountPage'
import { AdminLogin } from './pages/AdminLogin'
import { AdminPage } from './pages/AdminPage'
import { AdminPasswordReset } from './pages/AdminPasswordReset'
import { AdminAuthProvider } from './auth/AdminAuthContext'
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

export function App() {
  return (
    <QueryProvider>
      <AdminAuthProvider>
        <Routes>
          {/* Public routes - no authentication required */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          {/* Admin protected routes - must come BEFORE public routes so wildcard doesn't catch them */}
          <Route path="/admin/dashboard" element={<AdminPage />} />

          {/* Admin public routes - no authentication required */}
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route path="/admin/reset-password" element={<AdminPasswordReset />} />

          {/* User protected routes */}
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
              <Route path="/account" element={<AccountPage />} />
            </Route>
          </Route>

          {/* Fallback routes */}
          <Route path="/" element={<Navigate to="/restaurants" replace />} />
          <Route path="*" element={<Navigate to="/restaurants" replace />} />
        </Routes>
      </AdminAuthProvider>
    </QueryProvider>
  )
}
