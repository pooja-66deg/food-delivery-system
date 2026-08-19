import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQueryClient } from '@tanstack/react-query'

import { restaurantsApi } from '../api/restaurants'
import type { BrowseParams, Restaurant, RestaurantSuggestion } from '../api/restaurants'
import { errorMessage } from '../api/client'
import { Alert, Button, EmptyState, Loading, Thumb } from '../components/ui'
import { BrowseFilters, NO_FACETS } from '../components/BrowseFilters'
import { CityDropdown } from '../components/CityDropdown'
import { FavoriteButton } from '../components/FavoriteButton'
import type { Facets } from '../components/BrowseFilters'
import { PopularCuisines } from '../components/PopularCuisines'
import {
  RestaurantAvailabilityBadge,
  RestaurantCardHours,
} from '../components/RestaurantHours'
import { SearchSuggest } from '../components/SearchSuggest'
import { RatingStars } from '../reviews/RatingStars'
import { reviewCountLabel } from '../reviews/RatingSummary'
import { useRestaurantsList, usePopularCuisines } from '../hooks/queries/useRestaurantQueries'
import { useFavoriteIds } from '../hooks/queries/useFavoritesQuery'

const PAGE_SIZE = 12

const BAND_LABELS: Record<number, string> = { 1: '₹', 2: '₹₹', 3: '₹₹₹' }

export function RestaurantsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [city, setCity] = useState('')
  const [facets, setFacets] = useState<Facets>(NO_FACETS)
  // The term/filters the shown results were actually fetched for, so "matched
  // dishes" and the empty-state copy describe the results rather than what is
  // currently typed in the box.
  const [appliedSearch, setAppliedSearch] = useState('')

  // What actually drives the React Query fetch. Only updated when a search is
  // explicitly (re-)triggered — submit, a cuisine chip, or a filter change —
  // mirroring the old imperative `load()` calls rather than fetching on every
  // keystroke.
  const [queryParams, setQueryParams] = useState<BrowseParams>({
    ...NO_FACETS,
    limit: PAGE_SIZE,
    offset: 0,
  })

  // React Query owns page one (via queryParams above). Pages fetched by
  // "load more" accumulate here on top of it, and are reset whenever a new
  // search replaces queryParams.
  const [extraItems, setExtraItems] = useState<Restaurant[]>([])
  const [total, setTotal] = useState(0)
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null)
  // Next-page fetches are driven by scrolling, so they can be triggered far more
  // often than they complete. The state drives the footer copy; the ref is what
  // actually guards against firing a second request for the same offset, since
  // the observer callback can run again before a re-render lands.
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  const {
    data: page,
    isLoading,
    isError: isListError,
    error: listError,
  } = useRestaurantsList(queryParams)

  const { data: cuisines = [] } = usePopularCuisines()
  // Hearts are a nice-to-have too, and only customers have favourites — a 403
  // for any other role is swallowed inside the hook via initialData.
  const { data: favoriteIds = new Set<number>() } = useFavoriteIds()

  useEffect(() => {
    if (page) setTotal(page.total)
  }, [page])

  useEffect(() => {
    if (isListError) setTotal(0)
  }, [isListError])

  // A failed fetch clears the grid (same as the old catch block setting
  // `items([])`) rather than leaving stale results under the error banner.
  const items = isListError ? [] : page ? [...page.items, ...extraItems] : null

  // Overrides let a cuisine chip or a filter change search immediately with
  // its own value instead of racing the corresponding state update.
  const runSearch = (overrides?: { search?: string; city?: string; facets?: Facets }) => {
    const term = overrides?.search ?? search
    const place = overrides?.city ?? city
    const active = overrides?.facets ?? facets
    setAppliedSearch(term)
    setExtraItems([])
    setLoadMoreError(null)
    setQueryParams({
      ...active,
      search: term || undefined,
      city: place || undefined,
      // Paging is "load more" rather than numbered pages, so a fetch always
      // starts at the top and the list below is the whole loaded run.
      limit: PAGE_SIZE,
      offset: 0,
    })
  }

  const loadMore = async () => {
    if (!items || loadingMoreRef.current || items.length >= total) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const nextPage = await restaurantsApi.list({
        ...facets,
        search: appliedSearch || undefined,
        city: city || undefined,
        limit: PAGE_SIZE,
        offset: items.length,
      })
      setExtraItems((current) => [...current, ...nextPage.items])
      setTotal(nextPage.total)
    } catch (e) {
      setLoadMoreError(errorMessage(e, 'Failed to load more restaurants.'))
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }

  // Scroll pagination: the next page is fetched when a sentinel below the grid
  // comes into view, with a rootMargin so the fetch starts before the user
  // actually reaches the bottom and the grid grows without a visible stall.
  // Re-run on every length/total change so the observer follows the sentinel as
  // the list grows and detaches once everything is on screen.
  useEffect(() => {
    const node = sentinelRef.current
    // Guard rather than assume: environments without IntersectionObserver (older
    // browsers, jsdom) fall back to the Load more button, which is always there.
    if (!node || typeof IntersectionObserver === 'undefined') return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void loadMore()
      },
      { rootMargin: '300px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items?.length, total])

  const fetchSuggestions = useCallback((q: string) => restaurantsApi.suggest(q), [])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    runSearch()
  }

  // Picking a named restaurant means "take me there", not "filter by this text".
  const onSuggestionChosen = (s: RestaurantSuggestion) => navigate(`/restaurants/${s.id}`)

  const onCuisinePicked = (cuisine: string) => {
    setSearch(cuisine)
    runSearch({ search: cuisine })
  }

  // FavoriteButton performs its own optimistic add/remove call (and reverts on
  // failure) — it only reports the outcome here. Writing straight into the
  // `useFavoriteIds` cache keeps every page sharing that query in sync
  // immediately, without a second, redundant toggle call to the API.
  const onFavoriteToggled = (restaurantId: number, saved: boolean) =>
    queryClient.setQueryData<Set<number>>(['favorites', 'ids'], (current) => {
      const next = new Set(current ?? [])
      if (saved) next.add(restaurantId)
      else next.delete(restaurantId)
      return next
    })

  const onFacetsChanged = (next: Facets) => {
    setFacets(next)
    runSearch({ facets: next })
  }

  const error =
    loadMoreError ?? (isListError ? errorMessage(listError, 'Failed to load restaurants.') : null)

  return (
    <main className="app-main">
      <motion.div
        className="page-head"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
      >
        <span className="chip chip-accent">Discover</span>
        <h1 style={{ marginTop: '0.6rem' }}>Kitchens near you</h1>
        <p>Search a restaurant or a dish, then narrow by city, rating, price or diet.</p>
      </motion.div>

      <form className="toolbar" onSubmit={onSubmit}>
        <SearchSuggest
          value={search}
          onChange={setSearch}
          onSelect={onSuggestionChosen}
          fetchSuggestions={fetchSuggestions}
        />
        <CityDropdown
          value={city}
          onChange={setCity}
        />
        <Button type="submit">Search</Button>
      </form>

      <PopularCuisines cuisines={cuisines} onPick={onCuisinePicked} />

      <BrowseFilters value={facets} onChange={onFacetsChanged} />

      {error && <Alert>{error}</Alert>}

      {items === null || isLoading ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState>
          {appliedSearch
            ? `Nothing matched “${appliedSearch}”. Try another dish or clear a filter.`
            : 'No restaurants found. Try clearing a filter.'}
        </EmptyState>
      ) : (
        <>
          <p className="muted result-count">
            {total === 1 ? '1 kitchen' : `${total} kitchens`}
            {items.length < total ? ` · showing ${items.length}` : ''}
          </p>
        <div className="rest-grid">
          {items.map((r, i) => (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: Math.min(i * 0.04, 0.3) }}
            >
              <Link to={`/restaurants/${r.id}`} className="rest-card">
                <Thumb url={r.image_url} alt={`${r.name} cover`} variant="cover" />
                <div className="rest-card-top">
                  <RestaurantAvailabilityBadge restaurant={r} />
                  {r.cuisine && <span className="chip">{r.cuisine}</span>}
                  <FavoriteButton
                    restaurantId={r.id}
                    saved={favoriteIds.has(r.id)}
                    onToggled={onFavoriteToggled}
                  />
                </div>
                <h3>{r.name}</h3>
                {r.matched_items.length > 0 ? (
                  // Say why this result is here — a search for "biryani" turns up
                  // restaurants whose name and cuisine mention no such thing.
                  <p className="muted matched-dishes">
                    Serves {r.matched_items.slice(0, 3).join(', ')}
                    {r.matched_items.length > 3 ? ` +${r.matched_items.length - 3} more` : ''}
                  </p>
                ) : (
                  <p className="muted">{r.description ?? 'Freshly prepared meals.'}</p>
                )}
                <div className="rest-card-rating">
                  {r.rating_average === null ? (
                    // Not "0 stars" — an unrated kitchen is new, not bad.
                    <span className="chip">New</span>
                  ) : (
                    <>
                      <RatingStars value={r.rating_average} />
                      <span className="muted">
                        {r.rating_average} · {reviewCountLabel(r.review_count)}
                      </span>
                    </>
                  )}
                </div>
                <RestaurantCardHours restaurant={r} />
                <div className="rest-card-foot">
                  <span>
                    {r.city}
                    {r.price_band ? ` · ${BAND_LABELS[r.price_band]}` : ''}
                  </span>
                  <span>Min ₹{Number(r.min_order_amount).toFixed(2)}</span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
          {items.length < total && (
            // The sentinel is what scrolling into view triggers. The button stays
            // as an explicit control: it covers keyboard users, a failed auto-load
            // the reader wants to retry, and browsers without IntersectionObserver.
            <div className="load-more" ref={sentinelRef}>
              {loadingMore ? (
                <p className="muted" role="status">
                  Loading more kitchens…
                </p>
              ) : (
                <Button variant="ghost" onClick={() => void loadMore()}>
                  Load more
                </Button>
              )}
            </div>
          )}
          {items.length >= total && total > PAGE_SIZE && (
            <p className="muted load-more-end">That’s every kitchen matching your search.</p>
          )}
        </>
      )}
    </main>
  )
}
