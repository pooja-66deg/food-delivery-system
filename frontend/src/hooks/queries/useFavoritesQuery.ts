import { useQuery } from '@tanstack/react-query'
import { favoritesApi } from '../../api/favorites'

/**
 * Hook to fetch the set of favorite restaurant IDs for the current user.
 *
 * Returns the favorite restaurant IDs as a Set<number> for efficient lookup.
 * Initialized with an empty Set, updated with server data once fetched.
 */
export function useFavoriteIds() {
  return useQuery({
    queryKey: ['favorites', 'ids'],
    queryFn: async () => {
      const ids = await favoritesApi.ids()
      return new Set(ids)
    },
    staleTime: 1000 * 60 * 5,
    initialData: new Set(),
  })
}
