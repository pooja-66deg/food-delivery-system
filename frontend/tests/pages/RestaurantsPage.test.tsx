import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
}

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue([PIZZA])
  mocks.suggest.mockReset().mockResolvedValue([])
  mocks.popularCuisines.mockReset().mockResolvedValue([])
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
    mocks.list.mockResolvedValue([])
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
      expect(mocks.list).toHaveBeenLastCalledWith({ search: 'Italian', city: undefined }),
    )
  })

  it('passes the city filter through to the API', async () => {
    renderPage()
    await screen.findByText('Pizza Palace')

    await userEvent.type(screen.getByPlaceholderText('City'), 'gotham')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() =>
      expect(mocks.list).toHaveBeenLastCalledWith({ search: undefined, city: 'gotham' }),
    )
  })

  it('navigates to a restaurant chosen from the suggestions', async () => {
    mocks.suggest.mockResolvedValue([
      { id: 7, name: 'Pizza Palace', city: 'Metropolis', cuisine: 'Italian' },
    ])
    renderPage()
    await screen.findByText('Pizza Palace')

    await userEvent.type(screen.getByRole('combobox'), 'piz')
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
    mocks.list.mockResolvedValue([{ ...PIZZA, rating_average: 4.5, review_count: 2 }])
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
})
