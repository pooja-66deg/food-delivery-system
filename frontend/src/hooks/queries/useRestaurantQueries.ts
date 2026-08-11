import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { restaurantsApi } from '../../api/restaurants'
import type { BrowseParams } from '../../api/restaurants'

/**
 * Hook for browsing and searching restaurants with optional filters.
 * Automatically skips the fetch if no parameters are provided.
 *
 * Keeps the previous page's data visible while a new filter/search/page
 * fetch is in flight (`placeholderData: keepPreviousData`) so the grid
 * doesn't flash back to a loading state on every refinement — it only shows
 * the loading state before the very first successful fetch.
 */
export function useRestaurantsList(params?: BrowseParams) {
  return useQuery({
    queryKey: ['restaurants', 'list', params],
    queryFn: () => restaurantsApi.list(params),
    staleTime: 1000 * 60 * 5, // 5 minutes
    placeholderData: keepPreviousData,
  })
}

/**
 * Hook for the most popular cuisines, used as discovery chips on the browse
 * page. Rarely changes, so cached longer than the restaurant list itself.
 */
export function usePopularCuisines(limit?: number) {
  return useQuery({
    queryKey: ['restaurants', 'cuisines', 'popular', limit],
    queryFn: () => restaurantsApi.popularCuisines(limit),
    staleTime: 1000 * 60 * 10, // 10 minutes
  })
}

/**
 * Hook for fetching a single restaurant's details including menu.
 * Only enables the query if an id is provided.
 */
export function useRestaurantDetail(id: number | null | undefined) {
  return useQuery({
    queryKey: ['restaurants', 'detail', id],
    queryFn: () => restaurantsApi.get(id!),
    enabled: !!id,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })
}

/**
 * Hook for looking up multiple restaurants by their IDs.
 * Useful for hydrating favorites lists. Only enables if ids array is non-empty.
 */
export function useRestaurantLookup(ids: number[] | undefined) {
  return useQuery({
    queryKey: ['restaurants', 'lookup', ids],
    queryFn: () => restaurantsApi.lookup(ids!),
    enabled: !!ids && ids.length > 0,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })
}
