// Typed bindings for the delivery domain (driver-facing + customer tracking).

import { request } from './client'

export interface Coordinate {
  latitude: number
  longitude: number
}

export interface Delivery {
  id: number
  order_id: number
  driver_id: number | null
  status: string
  restaurant_name: string | null
  items: string | null
  order_total: string | null
  assigned_at: string | null
  picked_up_at: string | null
  delivered_at: string | null
  // Where this delivery is headed, for navigation. The driver cannot read the
  // tracking endpoint, so these ride along on their own assignments.
  restaurant: Coordinate | null
  destination: Coordinate | null
}

export interface Tracking {
  order_id: number
  status: string
  driver_id: number | null
  driver: Coordinate | null
  restaurant: Coordinate | null
  destination: Coordinate | null
  eta_minutes: number | null
  distance_km: number | null
  eta_source: 'google' | 'estimate' | null
}

export interface Driver {
  id: number
  first_name: string
  last_name: string
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
  setOnline: (online: boolean) =>
    request<{ driver_id: number; online: boolean }>('/delivery/status', {
      method: 'POST',
      auth: true,
      body: { online },
    }),
  postLocation: (latitude: number, longitude: number) =>
    request<{ driver_id: number; latitude: number; longitude: number }>('/delivery/location', {
      method: 'POST',
      auth: true,
      body: { latitude, longitude },
    }),
  availableDrivers: () => request<Driver[]>('/delivery/available-drivers', { auth: true }),
  reassign: (orderId: number, driverId: number) =>
    request<Delivery>(`/delivery/orders/${orderId}/reassign`, {
      method: 'POST',
      auth: true,
      body: { driver_id: driverId },
    }),
}
