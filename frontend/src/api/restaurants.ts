// Typed bindings for the restaurants domain.

import { request, upload } from './client'

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
  /** How far the restaurant delivers, in km. null means the owner has not set
   *  one and the platform default applies — not that it delivers anywhere. */
  delivery_radius_km: number | null
  image_url?: string | null
  /** Aggregated from reviews. null means nothing rated yet, never 0. */
  rating_average: number | null
  review_count: number
  /** 1–3 ($ / $$ / $$$) from average item price; null with no orderable items. */
  price_band: number | null
  /** Dish names that made this restaurant match the search term. */
  matched_items: string[]
}

export type RestaurantSort = 'name' | 'rating' | 'price_low' | 'price_high'

/** Every browse filter. All optional — omitted means "do not narrow by this". */
export interface BrowseParams {
  search?: string
  city?: string
  cuisine?: string
  min_rating?: number
  price_band?: number
  vegetarian_only?: boolean
  open_only?: boolean
  sort?: RestaurantSort
  limit?: number
  offset?: number
}

/** One page of results plus the size of the whole match. */
export interface RestaurantPage {
  items: Restaurant[]
  total: number
  limit: number
  offset: number
}

/** Trimmed restaurant shape returned by the typeahead endpoint. */
export interface RestaurantSuggestion {
  id: number
  name: string
  city: string
  cuisine: string | null
}

export interface CuisineCount {
  cuisine: string
  count: number
}

export interface MenuItem {
  id: number
  category_id: number
  name: string
  description: string | null
  price: number
  /** The owner's manual switch. */
  is_available: boolean
  /** null means stock is not tracked for this item. */
  stock_quantity: number | null
  is_vegetarian: boolean
  /** Server-derived: is_available AND stock allows it. Customers read this. */
  in_stock: boolean
  image_url?: string | null
}

export interface MenuCategory {
  id: number
  name: string
  sort_order: number
  items: MenuItem[]
}

export interface RestaurantDetail extends Restaurant {
  menu: MenuCategory[]
  /** Star -> review count. JSON keys arrive as strings. */
  rating_breakdown: Record<string, number>
}

export interface RestaurantCreateInput {
  name: string
  description?: string | null
  cuisine?: string | null
  city: string
  address_line: string
  phone: string
  min_order_amount: number
  /** Omit to accept the platform default. */
  delivery_radius_km?: number | null
}

export interface MenuItemCreateInput {
  category_id: number
  name: string
  description?: string | null
  price: number
  is_available?: boolean
  /** Send null to leave stock untracked, or stop tracking it. */
  stock_quantity?: number | null
  is_vegetarian?: boolean
}

export interface CategoryUpdateInput {
  name?: string
  sort_order?: number
}

export const restaurantsApi = {
  /**
   * Browse and search. Every filter is optional; only the ones set are sent, so
   * an unset filter never narrows the results (`vegetarian_only: false` would
   * be a filter, `undefined` is not).
   */
  list: (params?: BrowseParams) => {
    const q = new URLSearchParams()
    Object.entries(params ?? {}).forEach(([key, value]) => {
      if (value !== undefined && value !== '' && value !== false) q.set(key, String(value))
    })
    const qs = q.toString()
    return request<RestaurantPage>(`/restaurants${qs ? `?${qs}` : ''}`, { auth: true })
  },

  suggest: (q: string, limit = 8) =>
    request<RestaurantSuggestion[]>(
      `/restaurants/suggest?q=${encodeURIComponent(q)}&limit=${limit}`,
      { auth: true },
    ),

  popularCuisines: (limit = 8) =>
    request<CuisineCount[]>(`/restaurants/cuisines/popular?limit=${limit}`, { auth: true }),

  get: (id: number) => request<RestaurantDetail>(`/restaurants/${id}`, { auth: true }),

  // Owner management
  create: (body: RestaurantCreateInput) =>
    request<Restaurant>('/restaurants', { method: 'POST', body, auth: true }),

  update: (id: number, body: Partial<RestaurantCreateInput> & { is_open?: boolean }) =>
    request<Restaurant>(`/restaurants/${id}`, { method: 'PATCH', body, auth: true }),

  addCategory: (id: number, name: string) =>
    request<MenuCategory>(`/restaurants/${id}/categories`, { method: 'POST', body: { name }, auth: true }),

  updateCategory: (id: number, categoryId: number, body: CategoryUpdateInput) =>
    request<MenuCategory>(`/restaurants/${id}/categories/${categoryId}`, {
      method: 'PATCH',
      body,
      auth: true,
    }),

  // 409 when the category still holds items — the message names the count.
  deleteCategory: (id: number, categoryId: number) =>
    request<void>(`/restaurants/${id}/categories/${categoryId}`, {
      method: 'DELETE',
      auth: true,
    }),

  addItem: (id: number, body: MenuItemCreateInput) =>
    request<MenuItem>(`/restaurants/${id}/items`, { method: 'POST', body, auth: true }),

  updateItem: (id: number, itemId: number, body: Partial<MenuItemCreateInput>) =>
    request<MenuItem>(`/restaurants/${id}/items/${itemId}`, { method: 'PATCH', body, auth: true }),

  deleteItem: (id: number, itemId: number) =>
    request<void>(`/restaurants/${id}/items/${itemId}`, { method: 'DELETE', auth: true }),

  uploadImage: (id: number, file: File) =>
    upload<Restaurant>(`/restaurants/${id}/image`, file),

  uploadItemImage: (id: number, itemId: number, file: File) =>
    upload<MenuItem>(`/restaurants/${id}/items/${itemId}/image`, file),
}
