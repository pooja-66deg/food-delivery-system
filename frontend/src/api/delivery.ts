// Typed bindings for the delivery domain (driver-facing).

import { request } from './client'

export interface Delivery {
  id: number
  order_id: number
  driver_id: number | null
  status: string
  assigned_at: string | null
  picked_up_at: string | null
  delivered_at: string | null
}

export interface Tracking {
  order_id: number
  status: string
  driver_id: number | null
  location: { latitude: number; longitude: number } | null
}

export const deliveryApi = {
  assignments: () => request<Delivery[]>('/delivery/assignments', { auth: true }),
  accept: (orderId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/accept`, { method: 'POST', auth: true }),
  reject: (orderId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/reject`, { method: 'POST', auth: true }),
  pickup: (orderId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/pickup`, { method: 'POST', auth: true }),
  deliver: (orderId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/deliver`, { method: 'POST', auth: true }),
  tracking: (orderId: number) =>
    request<Tracking>(`/delivery/orders/${orderId}/tracking`, { auth: true }),
}
