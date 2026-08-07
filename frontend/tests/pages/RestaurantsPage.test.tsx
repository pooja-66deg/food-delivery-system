import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RestaurantsPage } from '../../src/pages/RestaurantsPage'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  suggest: vi.fn(),
  popularCuisines: vi.fn(),
}))

vi.mock('../../src/api/restaurants', () => ({
  restaurantsApi: {
    list: mocks.list,
    suggest: mocks.suggest,
    popularCuisines: mocks.popularCuisines,
  },
}))

const PIZZA = {
  id: 7,
  owner_id: 1,
  name: 'Pizza Palace',
  description: 'Wood-fired',
  cuisine: 'Italian',
  city: 'Metropolis',
  address_line: '1 St',
  phone: '+15550000000',
  is_open: true,
  min_order_amount: 10,
  rating_average: null,
  review_count: 0,
  price_band: 2,
  matched_items: [],
}

/** Browse returns a page envelope; helper keeps the fixtures readable. */
const page = (items: unknown[], total = items.length) => ({
  items,
  total,
  limit: 12,
  offset: 0,
})

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue(page([PIZZA]))
  mocks.suggest.mockReset().mockResolvedValue([])
  mocks.popularCuisines.mockReset().mockResolvedValue([])
})

/**
 * jsdom has no IntersectionObserver, so scroll pagination needs a stand-in. The
 * stub hands back a `scrollIntoView` that fires the page's callback the way a
 * real observer would when the sentinel below the grid enters the viewport.
 */
function stubIntersectionObserver() {
  const callbacks: IntersectionObserverCallback[] = []
  const stub = vi.fn((cb: IntersectionObserverCallback) => {
    callbacks.push(cb)
    return {
      observe: vi.fn(),
      disconnect: vi.fn(),
      unobserve: vi.fn(),
      takeRecords: vi.fn(),
      root: null,
      rootMargin: '',
      thresholds: [],
    }
  })
  vi.stubGlobal('IntersectionObserver', stub)
  return {
    /** Simulate the sentinel scrolling into view for every live observer. */
    scrollSentinelIntoView() {
      const entry = { isIntersecting: true } as IntersectionObserverEntry
      for (const cb of callbacks) cb([entry], {} as IntersectionObserver)
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/restaurants']}>
      <Routes>
        <Route path="/restaurants" element={<RestaurantsPage />} />
        <Route path="/restaurants/:id" element={<div>detail page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RestaurantsPage', () => {
  it('lists restaurants returned by the API', async () => {
    renderPage()

    expect(await screen.findByText('Pizza Palace')).toBeInTheDocument()
  })

  it('shows the empty state when nothing matches', async () => {
    mocks.list.mockResolvedValue(page([]))
    renderPage()

    expect(await screen.findByText(/no restaurants found/i)).toBeInTheDocument()
  })

  it('shows popular cuisine chips', async () => {
    mocks.popularCuisines.mockResolvedValue([{ cuisine: 'Italian', count: 3 }])
    renderPage()

    expect(await screen.findByRole('button', { name: 'Italian' })).toBeInTheDocument()
  })

  it('searches by cuisine when a chip is clicked', async () => {
    mocks.popularCuisines.mockResolvedValue([{ cuisine: 'Italian', count: 3 }])
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Italian' }))

    await waitFor(() =>
      expect(mocks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'Italian', city: undefined }),
      ),
    )
  })

  it('passes the city filter through to the API', async () => {
    renderPage()
    await screen.findByText('Pizza Palace')

    const cityInputs = screen.getAllByPlaceholderText(/search city|enter city/i)
    await userEvent.type(cityInputs[0], 'gotham')
    await userEvent.keyboard('{Enter}')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() =>
      expect(mocks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: undefined, city: 'gotham' }),
      ),
    )
  })

  it('navigates to a restaurant chosen from the suggestions', async () => {
    mocks.suggest.mockResolvedValue([
      { id: 7, name: 'Pizza Palace', city: 'Metropolis', cuisine: 'Italian' },
    ])
    renderPage()
    await screen.findByText('Pizza Palace')

    // Named explicitly: the sort control is a combobox too.
    await userEvent.type(screen.getByRole('combobox', { name: /search/i }), 'piz')
    await userEvent.click(await screen.findByRole('option', { name: /Pizza Palace/ }))

    expect(await screen.findByText('detail page')).toBeInTheDocument()
  })

  it('surfaces an error when the list request fails', async () => {
    mocks.list.mockRejectedValue(new Error('boom'))
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('still renders the page when popular cuisines cannot be loaded', async () => {
    mocks.popularCuisines.mockRejectedValue(new Error('boom'))
    renderPage()

    expect(await screen.findByText('Pizza Palace')).toBeInTheDocument()
  })

  it('shows a rated card with its stars and count', async () => {
    mocks.list.mockResolvedValue(page([{ ...PIZZA, rating_average: 4.5, review_count: 2 }]))
    renderPage()

    await screen.findByText('Pizza Palace')
    expect(screen.getByRole('img', { name: '4.5 out of 5' })).toBeInTheDocument()
    expect(screen.getByText(/2 reviews/)).toBeInTheDocument()
  })

  it('marks an unrated card as New rather than zero stars', async () => {
    // An unrated kitchen is new, not bad.
    renderPage()

    await screen.findByText('Pizza Palace')
    expect(screen.getByText('New')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /out of 5/ })).not.toBeInTheDocument()
  })
  it('shows the total match count and a load-more control when the page is short', async () => {
    mocks.list.mockResolvedValue(page([PIZZA], 30))
    renderPage()

    expect(await screen.findByText(/30 kitchens/)).toBeInTheDocument()
    expect(screen.getByText(/showing 1/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load more' })).toBeInTheDocument()
  })

  it('hides load-more once every match is on screen', async () => {
    renderPage()

    await screen.findByText('Pizza Palace')
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('load-more appends the next page at the right offset', async () => {
    const second = { ...PIZZA, id: 8, name: 'Second Spot' }
    mocks.list.mockResolvedValueOnce(page([PIZZA], 2)).mockResolvedValueOnce(page([second], 2))
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Second Spot')).toBeInTheDocument()
    // The first card stays — this is "load more", not "replace".
    expect(screen.getByText('Pizza Palace')).toBeInTheDocument()
    expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 1 }))
  })

  it('scrolling the sentinel into view loads the next page', async () => {
    const second = { ...PIZZA, id: 8, name: 'Second Spot' }
    mocks.list.mockResolvedValueOnce(page([PIZZA], 2)).mockResolvedValueOnce(page([second], 2))
    const observer = stubIntersectionObserver()
    renderPage()
    await screen.findByText('Pizza Palace')

    observer.scrollSentinelIntoView()

    expect(await screen.findByText('Second Spot')).toBeInTheDocument()
    expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 1 }))
  })

  it('scroll pagination fetches each offset once however often it fires', async () => {
    // A real observer fires repeatedly while the sentinel stays in view; without
    // an in-flight guard that would request the same offset several times.
    const second = { ...PIZZA, id: 8, name: 'Second Spot' }
    mocks.list.mockResolvedValueOnce(page([PIZZA], 2)).mockResolvedValue(page([second], 2))
    const observer = stubIntersectionObserver()
    renderPage()
    await screen.findByText('Pizza Palace')

    observer.scrollSentinelIntoView()
    observer.scrollSentinelIntoView()
    observer.scrollSentinelIntoView()

    await screen.findByText('Second Spot')
    // One initial list call plus exactly one next-page call.
    expect(mocks.list).toHaveBeenCalledTimes(2)
  })

  it('stops paginating once every match is loaded', async () => {
    const observer = stubIntersectionObserver()
    renderPage()
    await screen.findByText('Pizza Palace')

    observer.scrollSentinelIntoView()

    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(1))
  })

  it('a facet change refetches from the top with the facet applied', async () => {
    renderPage()
    await screen.findByText('Pizza Palace')

    await userEvent.click(screen.getByRole('button', { name: 'Vegetarian' }))

    await waitFor(() =>
      expect(mocks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ vegetarian_only: true, offset: 0 }),
      ),
    )
  })

  it('names the dishes that made a restaurant match', async () => {
    mocks.list.mockResolvedValue(
      page([{ ...PIZZA, matched_items: ['Margherita', 'Marinara'] }]),
    )
    renderPage()

    expect(await screen.findByText(/Serves Margherita, Marinara/)).toBeInTheDocument()
  })

  it('summarises a long dish match instead of listing everything', async () => {
    mocks.list.mockResolvedValue(
      page([{ ...PIZZA, matched_items: ['A', 'B', 'C', 'D', 'E'] }]),
    )
    renderPage()

    expect(await screen.findByText(/Serves A, B, C \+2 more/)).toBeInTheDocument()
  })

  it('shows the price band on a card', async () => {
    renderPage()

    const card = await screen.findByText('Pizza Palace')
    const cardBody = card.closest('.rest-card')
    expect(cardBody).toHaveTextContent(/Metropolis.*₹₹/s)
  })

  it('the empty state names the search that found nothing', async () => {
    mocks.list.mockResolvedValue(page([]))
    renderPage()
    await screen.findByText(/no restaurants found/i)

    await userEvent.type(screen.getByRole('combobox', { name: /search/i }), 'biryani')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText(/Nothing matched .biryani./)).toBeInTheDocument()
  })
})
