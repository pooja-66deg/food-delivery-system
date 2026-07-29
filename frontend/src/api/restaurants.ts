// Typed bindings for the restaurants domain.

import { request } from './client'

export interface Restaurant {
  id: number
  owner_id: number
  name: string
  description: string | null
  cuisine: string | null
  city: string
  address_line: string
  phone: string
  is_open: boolean
  min_order_amount: number
}

export interface MenuItem {
  id: number
  category_id: number
  name: string
  description: string | null
  price: number
  is_available: boolean
}

export interface MenuCategory {
  id: number
  name: string
  sort_order: number
  items: MenuItem[]
}

export interface RestaurantDetail extends Restaurant {
  menu: MenuCategory[]
}

export interface RestaurantCreateInput {
  name: string
  description?: string | null
  cuisine?: string | null
  city: string
  address_line: string
  phone: string
  min_order_amount: number
}

export interface MenuItemCreateInput {
  category_id: number
  name: string
  description?: string | null
  price: number
  is_available?: boolean
}

export const restaurantsApi = {
  list: (params?: { city?: string; search?: string }) => {
    const q = new URLSearchParams()
    if (params?.city) q.set('city', params.city)
    if (params?.search) q.set('search', params.search)
    const qs = q.toString()
    return request<Restaurant[]>(`/restaurants${qs ? `?${qs}` : ''}`, { auth: true })
  },

  get: (id: number) => request<RestaurantDetail>(`/restaurants/${id}`, { auth: true }),

  // Owner management
  create: (body: RestaurantCreateInput) =>
    request<Restaurant>('/restaurants', { method: 'POST', body, auth: true }),

  update: (id: number, body: Partial<RestaurantCreateInput> & { is_open?: boolean }) =>
    request<Restaurant>(`/restaurants/${id}`, { method: 'PATCH', body, auth: true }),

  addCategory: (id: number, name: string) =>
    request<MenuCategory>(`/restaurants/${id}/categories`, { method: 'POST', body: { name }, auth: true }),

  addItem: (id: number, body: MenuItemCreateInput) =>
    request<MenuItem>(`/restaurants/${id}/items`, { method: 'POST', body, auth: true }),

  updateItem: (id: number, itemId: number, body: Partial<MenuItemCreateInput>) =>
    request<MenuItem>(`/restaurants/${id}/items/${itemId}`, { method: 'PATCH', body, auth: true }),
}
