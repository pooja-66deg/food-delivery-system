import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OwnerPage } from '../../../src/pages/owner/OwnerPage'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  forRestaurant: vi.fn(),
  auth: { user: { id: 1, role: 'restaurant' } as { id: number; role: string } | null },
}))

vi.mock('../../../src/api/restaurants', () => ({
  restaurantsApi: { list: mocks.list, get: mocks.get, create: mocks.create },
}))

vi.mock('../../../src/api/orders', () => ({
  ordersApi: { forRestaurant: mocks.forRestaurant },
}))

vi.mock('../../../src/auth/AuthContext', () => ({ useAuth: () => mocks.auth }))

// The opened venue is a whole subtree that fetches for itself. This page's job
// is only to open the right one, so it stands in as a marker.
vi.mock('../../../src/pages/owner/RestaurantWorkspace', () => ({
  RestaurantWorkspace: ({
    restaurantId,
    ordersToday,
    onBack,
  }: {
    restaurantId: number
    ordersToday: number
    onBack: () => void
  }) => (
    <div>
      <p>workspace for {restaurantId}</p>
      <p>orders today: {ordersToday}</p>
      <button type="button" onClick={onBack}>
        back
      </button>
    </div>
  ),
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
  delivery_radius_km: null,
  rating_average: null,
  review_count: 0,
  price_band: 2,
  matched_items: [],
  image_url: null,
}

const CURRY = {
  ...PIZZA,
  id: 8,
  name: 'Curry House',
  city: 'Gotham',
  cuisine: 'Thai',
  is_open: false,
}

/** A detail payload with one category holding the given items. */
const detailFor = (base: typeof PIZZA, items: { stock_quantity: number | null }[]) => ({
  ...base,
  rating_breakdown: {},
  menu: [
    {
      id: 1,
      name: 'Mains',
      sort_order: 0,
      items: items.map((item, i) => ({
        id: 100 + i,
        category_id: 1,
        name: `Dish ${i}`,
        description: null,
        price: 9,
        is_available: true,
        is_vegetarian: false,
        in_stock: true,
        image_url: null,
        ...item,
      })),
    },
  ],
})

/** An order awaiting the owner's accept/reject decision. */
const order = (overrides: Record<string, unknown> = {}) => ({
  id: 1042,
  customer_id: 5,
  restaurant_id: 7,
  address_id: 2,
  status: 'PAYMENT_SUCCESS',
  payment_method: 'CARD',
  payment_status: 'SUCCESS',
  subtotal: 20,
  delivery_fee: 2,
  total: 22,
  refund_status: 'NONE',
  refund_amount: 0,
  cancelled_by: null,
  cancel_reason: null,
  created_at: new Date().toISOString(),
  items: [{ menu_item_id: 1, name: 'Margherita', unit_price: 10, quantity: 2, line_total: 20 }],
  events: [],
  ...overrides,
})

beforeEach(() => {
  mocks.auth.user = { id: 1, role: 'restaurant' }
  mocks.list
    .mockReset()
    .mockResolvedValue({ items: [PIZZA, CURRY], total: 2, limit: 100, offset: 0 })
  mocks.get.mockReset().mockImplementation((id: number) =>
    Promise.resolve(detailFor(id === 7 ? PIZZA : CURRY, [{ stock_quantity: null }])),
  )
  mocks.forRestaurant.mockReset().mockResolvedValue([])
  mocks.create.mockReset()
})

describe('OwnerPage access', () => {
  it('turns away accounts that do not own restaurants', () => {
    mocks.auth.user = { id: 2, role: 'customer' }
    render(<OwnerPage />)

    expect(screen.getByText(/for restaurant accounts/i)).toBeInTheDocument()
  })

  it('lists only the restaurants this owner owns', async () => {
    mocks.list.mockResolvedValue({
      items: [PIZZA, { ...CURRY, owner_id: 99 }],
      total: 2,
      limit: 100,
      offset: 0,
    })
    render(<OwnerPage />)

    expect(await screen.findByRole('button', { name: /Pizza Palace/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Curry House/ })).not.toBeInTheDocument()
  })

  it('surfaces a failure to load the list', async () => {
    mocks.list.mockRejectedValue(new Error('boom'))
    render(<OwnerPage />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('prompts for a first restaurant when there are none', async () => {
    mocks.list.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 })
    render(<OwnerPage />)

    expect(await screen.findByText(/No restaurants assigned yet/)).toBeInTheDocument()
  })
})

describe('OwnerPage stat tiles', () => {
  it('counts the owner’s restaurants', async () => {
    render(<OwnerPage />)

    const tile = (
      await screen.findByText('Restaurants', { selector: '.stat-label' })
    ).closest('.stat-tile')
    expect(tile).toHaveTextContent('2')
  })

  it('counts only orders the kitchen still owes', async () => {
    // Delivered is done; awaiting-accept and preparing are not.
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(
        id === 7
          ? [order(), order({ id: 2, status: 'DELIVERED' })]
          : [order({ id: 3, restaurant_id: 8, status: 'PREPARING' })],
      ),
    )
    render(<OwnerPage />)

    const tile = (await screen.findByText('Live orders')).closest('.stat-tile')
    await waitFor(() => expect(tile).toHaveTextContent('2'))
  })

  it('totals today’s order value across restaurants', async () => {
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(id === 7 ? [order({ total: 22.5 })] : [order({ id: 3, total: 10 })]),
    )
    render(<OwnerPage />)

    const tile = (await screen.findByText('Order value today')).closest('.stat-tile')
    await waitFor(() => expect(tile).toHaveTextContent('₹32.50'))
  })

  it('leaves out cancelled orders, which are not trade', async () => {
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(id === 7 ? [order({ total: 22.5, status: 'CANCELLED' })] : []),
    )
    render(<OwnerPage />)

    const tile = (await screen.findByText('Order value today')).closest('.stat-tile')
    await waitFor(() => expect(tile).toHaveTextContent('₹0.00'))
  })
})

describe('OwnerPage restaurant rows', () => {
  it('summarises each menu once its detail arrives', async () => {
    render(<OwnerPage />)

    expect(await screen.findByText(/Italian · 1 category · 1 dish/)).toBeInTheDocument()
  })

  it('warns about dishes running out', async () => {
    mocks.get.mockImplementation((id: number) =>
      Promise.resolve(
        detailFor(id === 7 ? PIZZA : CURRY, [{ stock_quantity: 2 }, { stock_quantity: null }]),
      ),
    )
    render(<OwnerPage />)

    expect((await screen.findAllByText('1 low stock')).length).toBe(2)
  })

  it('says nothing about stock that is not tracked', async () => {
    render(<OwnerPage />)
    await screen.findByRole('button', { name: /Pizza Palace/ })

    expect(screen.queryByText(/low stock/)).not.toBeInTheDocument()
  })

  it('marks a closed restaurant on its row', async () => {
    render(<OwnerPage />)

    const row = await screen.findByRole('button', { name: /Curry House/ })
    expect(row).toHaveTextContent('Closed')
    expect(await screen.findByRole('button', { name: /Pizza Palace/ })).not.toHaveTextContent(
      'Closed',
    )
  })

  it('still lists a restaurant whose menu could not be fetched', async () => {
    // One failed detail must not blank the row or take the page down.
    mocks.get.mockRejectedValue(new Error('boom'))
    render(<OwnerPage />)

    expect(await screen.findByRole('button', { name: /Pizza Palace/ })).toBeInTheDocument()
  })
})

describe('OwnerPage opening a venue', () => {
  it('opens the restaurant that was clicked', async () => {
    render(<OwnerPage />)

    await userEvent.click(await screen.findByRole('button', { name: /Curry House/ }))

    expect(await screen.findByText('workspace for 8')).toBeInTheDocument()
  })

  it('shows the dashboard, not a venue, on arrival', async () => {
    render(<OwnerPage />)
    await screen.findByRole('button', { name: /Pizza Palace/ })

    expect(screen.queryByText(/workspace for/)).not.toBeInTheDocument()
  })

  it('goes back to the dashboard from a venue', async () => {
    render(<OwnerPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Pizza Palace/ }))
    await screen.findByText('workspace for 7')

    await userEvent.click(screen.getByRole('button', { name: 'back' }))

    expect(await screen.findByRole('button', { name: /Pizza Palace/ })).toBeInTheDocument()
  })
})

describe('OwnerPage creating a restaurant', () => {
  it('keeps the create form behind a button rather than on the page', async () => {
    mocks.auth.user = { id: 1, role: 'admin' }
    render(<OwnerPage />)
    await screen.findByRole('button', { name: /Pizza Palace/ })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /New restaurant/ }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
  })

  it('a created restaurant closes the dialog and opens its venue', async () => {
    mocks.auth.user = { id: 1, role: 'admin' }
    const created = { ...PIZZA, id: 9, name: 'New Spot' }
    mocks.create.mockResolvedValue(created)
    render(<OwnerPage />)
    await screen.findByRole('button', { name: /Pizza Palace/ })

    await userEvent.click(screen.getByRole('button', { name: /New restaurant/ }))
    await userEvent.type(screen.getByLabelText('Name'), 'New Spot')
    const cityInputs = screen.getAllByPlaceholderText(/search city|enter city/i)
    await userEvent.type(cityInputs[0], 'Metropolis')
    await userEvent.keyboard('{Enter}')
    await userEvent.type(screen.getByPlaceholderText('Street address'), '2 St')
    await userEvent.type(screen.getByLabelText('Phone'), '5550000000')
    // The refetch has to include the new restaurant for it to be openable.
    mocks.list.mockResolvedValue({
      items: [PIZZA, CURRY, created],
      total: 3,
      limit: 100,
      offset: 0,
    })

    await userEvent.click(screen.getByRole('button', { name: 'Create restaurant' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByText('workspace for 9')).toBeInTheDocument()
  })
})

describe('OwnerPage order queue', () => {
  it('shows a ticket for each live order with its kitchen named', async () => {
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(id === 7 ? [order()] : []),
    )
    render(<OwnerPage />)

    expect(await screen.findByText(/#1042 · Pizza Palace/)).toBeInTheDocument()
    expect(screen.getByText('2 × Margherita')).toBeInTheDocument()
  })

  it('offers accept and reject on an order awaiting a decision', async () => {
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(id === 7 ? [order()] : []),
    )
    render(<OwnerPage />)
    await screen.findByText(/#1042/)

    expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  })

  it('says the queue is empty rather than showing nothing', async () => {
    render(<OwnerPage />)

    expect(await screen.findByText(/Nothing in the queue/)).toBeInTheDocument()
  })

  it('keeps finished orders out of the queue', async () => {
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(id === 7 ? [order({ status: 'DELIVERED' })] : []),
    )
    render(<OwnerPage />)

    expect(await screen.findByText(/Nothing in the queue/)).toBeInTheDocument()
  })

  it('puts the newest ticket at the top', async () => {
    const older = order({ id: 1000, created_at: new Date(Date.now() - 3_600_000).toISOString() })
    const newer = order({ id: 1001 })
    mocks.forRestaurant.mockImplementation((id: number) =>
      Promise.resolve(id === 7 ? [older, newer] : []),
    )
    render(<OwnerPage />)
    await screen.findByText(/#1001/)

    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(titles[0]).toContain('#1001')
  })
})
