// Typed bindings for the admin panel.

import { request } from './client'

export interface AdminStats {
  users: number
  restaurants: number
  orders_total: number
  orders_by_status: Record<string, number>
  gross_merchandise_value: number
}

export interface AdminUser {
  id: number
  email: string
  phone: string
  first_name: string
  last_name: string
  role: string
  is_active: boolean
  created_at: string
}

export interface AdminOrder {
  id: number
  customer_id: number
  restaurant_id: number
  status: string
  payment_status: string
  total: number
  created_at: string
}

export const adminApi = {
  stats: () => request<AdminStats>('/admin/stats', { auth: true }),
  users: () => request<AdminUser[]>('/admin/users', { auth: true }),
  orders: () => request<AdminOrder[]>('/admin/orders', { auth: true }),
  runTimeoutSweep: () =>
    request<{ expired: number }>('/admin/expire-acceptances', { method: 'POST', auth: true }),
}
