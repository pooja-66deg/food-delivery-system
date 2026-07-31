// Typed bindings for the cart domain.

import { request } from './client'

export interface CartItem {
  menu_item_id: number
  name: string
  unit_price: number
  quantity: number
  line_total: number
}

export interface CartView {
  restaurant_id: number | null
  items: CartItem[]
  subtotal: number
  price_hash: string
}

export const cartApi = {
  get: () => request<CartView>('/cart', { auth: true }),

  add: (menu_item_id: number, quantity = 1) =>
    request<CartView>('/cart/items', { method: 'POST', body: { menu_item_id, quantity }, auth: true }),

  update: (menuItemId: number, quantity: number) =>
    request<CartView>(`/cart/items/${menuItemId}`, { method: 'PATCH', body: { quantity }, auth: true }),

  remove: (menuItemId: number) =>
    request<CartView>(`/cart/items/${menuItemId}`, { method: 'DELETE', auth: true }),

  clear: () => request<void>('/cart', { method: 'DELETE', auth: true }),
}
