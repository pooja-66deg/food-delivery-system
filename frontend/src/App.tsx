import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AccountPage } from './pages/account/AccountPage'
import { AdminPage } from './pages/AdminPage'
import { CartPage } from './pages/CartPage'
import { DriverPage } from './pages/DriverPage'
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
import { VerifyEmailPage } from './pages/VerifyEmailPage'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      {/* Public: the link is opened from a mail client that may not be signed in. */}
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/restaurants" element={<RestaurantsPage />} />
          <Route path="/restaurants/:id" element={<RestaurantDetailPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:id" element={<OrderDetailPage />} />
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/deliveries" element={<DriverPage />} />
          <Route path="/manage" element={<OwnerPage />} />
          <Route path="/restaurant/orders" element={<RestaurantOrdersPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/restaurants" replace />} />
      <Route path="*" element={<Navigate to="/restaurants" replace />} />
    </Routes>
  )
}
