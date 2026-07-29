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

export const deliveryApi = {
  assignments: () => request<Delivery[]>('/delivery/assignments', { auth: true }),
  pickup: (orderId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/pickup`, { method: 'POST', auth: true }),
  deliver: (orderId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/deliver`, { method: 'POST', auth: true }),
}
