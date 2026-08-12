// Typed bindings for the orders + payments domains.

import { request } from './client'
import type { AuthAs } from './client'

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
  payment_checkout_url?: string | null
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
  /** Only returned by `resume`, for an order still awaiting card payment. */
  checkout_url?: string | null
}

export type PaymentMethod = 'COD' | 'CARD'

/** Which slice of the customer's history to list. */
export type OrderScope = 'active' | 'past' | 'all'

export const ordersApi = {
  checkout: (address_id: number, price_hash: string, payment_method: PaymentMethod = 'COD') =>
    request<Order>('/orders/checkout', {
      method: 'POST',
      body: { address_id, price_hash, payment_method },
      auth: true,
    }),

  list: (scope: OrderScope = 'all') =>
    request<OrderSummary[]>(`/orders?scope=${scope}`, { auth: true }),

  forRestaurant: (restaurantId: number) =>
    request<Order[]>(`/orders/restaurant/${restaurantId}`, { auth: true }),

  get: (id: number) => request<Order>(`/orders/${id}`, { auth: true }),

  cancel: (id: number) => request<Order>(`/orders/${id}/cancel`, { method: 'POST', auth: true }),

  payment: (orderId: number) => request<Payment>(`/payments/order/${orderId}`, { auth: true }),

  /** Open a fresh hosted checkout for an order left unpaid. */
  resumePayment: (orderId: number) =>
    request<Payment>(`/payments/order/${orderId}/resume`, { method: 'POST', auth: true }),

  // Restaurant/admin actions
  accept: (id: number) => request<Order>(`/orders/${id}/accept`, { method: 'POST', auth: true }),

  reject: (id: number, reason?: string) =>
    request<Order>(`/orders/${id}/reject`, { method: 'POST', body: { reason }, auth: true }),

  /** Advance an order. The owner's ticket and the operator console both call
   *  this, and the endpoint accepts either role — so the caller says which
   *  session it is acting as rather than leaving the client to guess. */
  setStatus: (id: number, status: string, auth: AuthAs = true) =>
    request<Order>(`/orders/${id}/status`, { method: 'POST', body: { status }, auth }),
}
