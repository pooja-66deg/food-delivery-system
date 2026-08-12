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
  /** Whether an operator has let this venue trade. Customers only ever see
   *  'approved' — browse returns nothing else — but the owner dashboard renders
   *  the same shape and needs the other two. */
  approval_status: ApprovalStatus
  /** Only set when rejected: what the owner has to fix. */
  rejection_reason: string | null
  food_type: FoodType
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

export type ApprovalStatus = 'pending' | 'approved' | 'rejected'

/** What a kitchen serves, as its owner declares it. The customer Vegetarian
 *  filter reads this rather than inferring from which dishes are flagged. */
export type FoodType = 'veg' | 'non_veg' | 'both'

export const FOOD_TYPE_LABELS: Record<FoodType, string> = {
  veg: 'Vegetarian',
  non_veg: 'Non-vegetarian',
  both: 'Veg & Non-veg',
}

/** Every food type, in display order — for populating a picker.
 *
 *  Derived from the labels rather than listed again, so a type added there
 *  appears in every picker without a second edit. Exported because two forms
 *  now offer the choice: the owner's settings, and restaurant sign-up. */
export const FOOD_TYPES = Object.keys(FOOD_TYPE_LABELS) as FoodType[]

/** One line of the admin restaurant list: a restaurant plus who owns it. */
export interface AdminRestaurantRow extends Restaurant {
  /** Empty when no user event has been seen for that owner yet — the list
   *  still shows the venue, since an operator needs to see it either way. */
  owner_name: string
}

export interface AdminRestaurantPage {
  items: AdminRestaurantRow[]
  total: number
  limit: number
  offset: number
}

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

export interface CitiesResponse {
  cities: string[]
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
  food_type?: FoodType
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

  listCities: () => request<CitiesResponse>('/restaurants/cities', { auth: true }),

  /** The cards behind a set of ids — how a favourites list is hydrated.
   *  Favourites live in the users service and can only store ids. */
  lookup: (ids: number[]) =>
    request<Restaurant[]>(`/restaurants/lookup?ids=${ids.join(',')}`, { auth: true }),

  get: (id: number) => request<RestaurantDetail>(`/restaurants/${id}`, { auth: true }),

  /** The signed-in owner's own restaurants, whatever their approval status.
   *
   *  Not browse-filtered-by-owner: browse returns approved venues only, so an
   *  owner waiting on approval would see an empty dashboard and reasonably
   *  conclude their registration was lost. */
  mine: () => request<Restaurant[]>('/restaurants/mine', { auth: true }),

  /** Every restaurant on the platform, for the operator console. Admin only. */
  adminList: (approvalStatus?: ApprovalStatus) =>
    request<AdminRestaurantPage>(
      `/restaurants/admin/all?limit=100${approvalStatus ? `&approval_status=${approvalStatus}` : ''}`,
      { auth: 'admin' },
    ),

  /** Approve or reject a venue. Admin only. */
  decideApproval: (id: number, status: 'approved' | 'rejected', reason?: string) =>
    request<AdminRestaurantRow>(`/restaurants/${id}/approval`, {
      method: 'POST',
      body: { status, reason: reason ?? null },
      auth: 'admin',
    }),

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
