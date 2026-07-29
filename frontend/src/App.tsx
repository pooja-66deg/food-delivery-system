import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AccountPage } from './pages/AccountPage'
import { AdminPage } from './pages/AdminPage'
import { CartPage } from './pages/CartPage'
import { DriverPage } from './pages/DriverPage'
import { LoginPage } from './pages/LoginPage'
import { OrderDetailPage } from './pages/OrderDetailPage'
import { OrdersPage } from './pages/OrdersPage'
import { OwnerPage } from './pages/OwnerPage'
import { RegisterPage } from './pages/RegisterPage'
import { RestaurantsPage } from './pages/RestaurantsPage'
import { RestaurantDetailPage } from './pages/RestaurantDetailPage'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/restaurants" element={<RestaurantsPage />} />
          <Route path="/restaurants/:id" element={<RestaurantDetailPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:id" element={<OrderDetailPage />} />
          <Route path="/deliveries" element={<DriverPage />} />
          <Route path="/manage" element={<OwnerPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/restaurants" replace />} />
      <Route path="*" element={<Navigate to="/restaurants" replace />} />
    </Routes>
  )
}
