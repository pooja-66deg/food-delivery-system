import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RestaurantDetailPage } from '../../src/pages/RestaurantDetailPage'

const mocks = vi.hoisted(() => ({
  detail: null as Record<string, unknown> | null,
}))

vi.mock('../../src/api/restaurants', () => ({
  restaurantsApi: { get: () => Promise.resolve(mocks.detail) },
}))

vi.mock('../../src/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'customer' } }),
}))

vi.mock('../../src/cart/CartContext', () => ({
  useCart: () => ({ add: () => Promise.resolve() }),
}))

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 11,
    category_id: 3,
    name: 'Margherita',
    description: 'Tomato and basil',
    price: 10,
    is_available: true,
    stock_quantity: null,
    in_stock: true,
    image_url: null,
    ...overrides,
  }
}

function withMenu(items: Record<string, unknown>[], restaurant: Record<string, unknown> = {}) {
  mocks.detail = {
    id: 1,
    owner_id: 2,
    name: 'Pizza Palace',
    description: 'Wood fired',
    cuisine: 'Italian',
    city: 'Metropolis',
    address_line: '1 Main St',
    phone: '+15550000000',
    is_open: true,
    min_order_amount: 5,
    image_url: null,
    menu: [{ id: 3, name: 'Mains', sort_order: 0, items }],
    ...restaurant,
  }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/restaurants/1']}>
      <Routes>
        <Route path="/restaurants/:id" element={<RestaurantDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.detail = null
})

describe('RestaurantDetailPage stock display', () => {
  it('offers an in-stock item', async () => {
    withMenu([item()])
    renderPage()

    const add = await screen.findByRole('button', { name: 'Add' })
    expect(add).toBeEnabled()
    expect(screen.queryByText('Out of stock')).not.toBeInTheDocument()
  })

  it('marks a sold-out item and disables ordering', async () => {
    withMenu([item({ stock_quantity: 0, in_stock: false })])
    renderPage()

    expect(await screen.findByText('Out of stock')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unavailable' })).toBeDisabled()
  })

  it('marks an item the owner turned off, even with stock left', async () => {
    withMenu([item({ is_available: false, stock_quantity: 9, in_stock: false })])
    renderPage()

    expect(await screen.findByText('Out of stock')).toBeInTheDocument()
  })

  it('warns when only a few are left', async () => {
    withMenu([item({ stock_quantity: 2 })])
    renderPage()

    expect(await screen.findByText('Only 2 left')).toBeInTheDocument()
  })

  it('stays quiet about a healthy count', async () => {
    withMenu([item({ stock_quantity: 40 })])
    renderPage()

    await screen.findByRole('button', { name: 'Add' })
    expect(screen.queryByText(/left$/)).not.toBeInTheDocument()
  })

  it('says nothing about stock for an untracked item', async () => {
    withMenu([item()])
    renderPage()

    await screen.findByRole('button', { name: 'Add' })
    expect(screen.queryByText(/left$/)).not.toBeInTheDocument()
  })
})

describe('RestaurantDetailPage images', () => {
  it('renders an uploaded item image', async () => {
    withMenu([item({ image_url: '/media/items/11.jpg' })])
    renderPage()

    const img = await screen.findByAltText('Margherita')
    expect(img).toHaveAttribute('src', '/api/media/items/11.jpg')
  })

  it('renders an uploaded cover image', async () => {
    withMenu([item()], { image_url: '/media/restaurants/1.jpg' })
    renderPage()

    const img = await screen.findByAltText('Pizza Palace cover')
    expect(img).toHaveAttribute('src', '/api/media/restaurants/1.jpg')
  })

  it('falls back to a placeholder when there is no image', async () => {
    withMenu([item()])
    renderPage()

    await screen.findByRole('button', { name: 'Add' })
    expect(screen.queryByAltText('Margherita')).not.toBeInTheDocument()
    expect(document.querySelector('.item-placeholder')).toBeTruthy()
  })
})
