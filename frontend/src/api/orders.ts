// Typed bindings for the orders + payments domains.

import { request } from './client'

export interface OrderItem {
  menu_item_id: number
  name: string
  unit_price: number
  quantity: number
  line_total: number
}

export interface OrderEvent {
  from_status: string | null
  to_status: string
  actor: string
  reason: string | null
  at: string
}

export interface Order {
  id: number
  customer_id: number
  restaurant_id: number
  address_id: number
  status: string
  payment_method: string
  payment_status: string
  subtotal: number
  delivery_fee: number
  total: number
  refund_status: string
  refund_amount: number
  cancelled_by: string | null
  cancel_reason: string | null
  created_at: string
  items: OrderItem[]
  events: OrderEvent[]
}

export interface OrderSummary {
  id: number
  restaurant_id: number
  status: string
  total: number
  created_at: string
}

export interface Payment {
  id: number
  order_id: number
  provider: string
  amount: number
  status: string
  provider_ref: string | null
  created_at: string
}

export const ordersApi = {
  checkout: (address_id: number, price_hash: string) =>
    request<Order>('/orders/checkout', { method: 'POST', body: { address_id, price_hash }, auth: true }),

  list: () => request<OrderSummary[]>('/orders', { auth: true }),

  get: (id: number) => request<Order>(`/orders/${id}`, { auth: true }),

  cancel: (id: number) => request<Order>(`/orders/${id}/cancel`, { method: 'POST', auth: true }),

  payment: (orderId: number) => request<Payment>(`/payments/order/${orderId}`, { auth: true }),

  // Restaurant/admin actions
  accept: (id: number) => request<Order>(`/orders/${id}/accept`, { method: 'POST', auth: true }),

  reject: (id: number, reason?: string) =>
    request<Order>(`/orders/${id}/reject`, { method: 'POST', body: { reason }, auth: true }),

  setStatus: (id: number, to: string) =>
    request<Order>(`/orders/${id}/status`, { method: 'POST', body: { to }, auth: true }),
}
