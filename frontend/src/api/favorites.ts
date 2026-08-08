// Typed bindings for favourite restaurants.
//
// Favourites are stored by the users service, which can only hold ids — a
// restaurant lives in another service's database and cannot be joined to. So
// `list` is two calls: which ones, then what they are. Each is served entirely
// by the service that owns the answer, and a slow restaurants service degrades
// this page rather than breaking it.

import { request } from './client'
import { restaurantsApi } from './restaurants'
import type { Restaurant } from './restaurants'

export const favoritesApi = {
  /** Ids only — enough for a browse page to fill in the saved hearts. */
  ids: () => request<number[]>('/favorites/ids', { auth: true }),

  /** Saved restaurants in full, most recently saved first. */
  list: async (): Promise<Restaurant[]> => {
    const ids = await request<number[]>('/favorites', { auth: true })
    if (ids.length === 0) return []
    const found = await restaurantsApi.lookup(ids)
    // Restored to the saved order: the lookup answers by id, not by when it was
    // saved, and "most recently saved first" is what the page promises.
    const byId = new Map(found.map((r) => [r.id, r]))
    return ids.map((id) => byId.get(id)).filter((r): r is Restaurant => r !== undefined)
  },

  /** Idempotent: saving an already-saved restaurant is not an error. */
  add: (restaurantId: number) =>
    request<void>('/favorites', {
      method: 'POST',
      body: { restaurant_id: restaurantId },
      auth: true,
    }),

  remove: (restaurantId: number) =>
    request<void>(`/favorites/${restaurantId}`, { method: 'DELETE', auth: true }),
}
