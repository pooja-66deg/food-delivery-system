// Placing a card order.
//
// The interesting part is what changed underneath. Checkout used to create the
// payment inline and hand back Stripe's hosted URL with the order. The payments
// service creates it from the order event now — asynchronously, which is what
// stops a slow card provider holding up order creation — so the URL is no
// longer in the checkout response and has to be polled for.
//
// Three outcomes matter, and all three are here: it arrives, it arrives late,
// and it never arrives.

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CartPage } from '../../src/pages/CartPage'
import { QueryProvider } from '../../src/providers/QueryProvider'

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const checkout = vi.fn()
const resume = vi.fn()
const getCart = vi.fn()
vi.mock('../../src/api/orders', () => ({ ordersApi: { checkout: (...a: unknown[]) => checkout(...a) } }))
vi.mock('../../src/api/payments', () => ({ paymentsApi: { resume: (...a: unknown[]) => resume(...a) } }))
vi.mock('../../src/api/cart', () => ({ cartApi: { get: (...a: unknown[]) => getCart(...a) } }))
vi.mock('../../src/api/auth', () => ({
  authApi: {
    listAddresses: () =>
      Promise.resolve([
        { id: 5, label: 'home', line1: '22 Elm St', city: 'Metropolis',
          postal_code: '12345', is_default: true },
      ]),
  },
}))

/** Where the browser was sent, without actually navigating in jsdom. */
let assigned: string | null = null

beforeEach(() => {
  vi.clearAllMocks()
  assigned = null
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      get href() {
        return assigned ?? ''
      },
      set href(value: string) {
        assigned = value
      },
    },
  })
  checkout.mockResolvedValue({ id: 77, status: 'PAYMENT_PENDING', payment_checkout_url: null })
  getCart.mockResolvedValue({
    restaurant_id: 10,
    items: [{ menu_item_id: 1, name: 'Pizza', unit_price: 12, quantity: 1, line_total: 12 }],
    subtotal: 12,
    price_hash: 'hash',
  })
})

afterEach(() => {
  vi.useRealTimers()
})

async function placeCardOrder() {
  const user = userEvent.setup()
  render(
    <QueryProvider>
      <MemoryRouter>
        <CartPage />
      </MemoryRouter>
    </QueryProvider>,
  )
  await screen.findByText(/Pizza/)
  await user.click(screen.getByRole('button', { name: /card \(online\)/i }))
  await user.click(screen.getByRole('button', { name: /place order \(card\)/i }))
}

describe('placing a card order', () => {
  it('sends the browser to the hosted page once the URL appears', async () => {
    resume.mockResolvedValue({ id: 1, checkout_url: 'https://checkout.stripe.test/session' })

    await placeCardOrder()

    await waitFor(() => expect(assigned).toBe('https://checkout.stripe.test/session'))
    expect(navigate).not.toHaveBeenCalled()
  })

  it('keeps asking while the order event is still in flight', async () => {
    // A 404 here is not an error: it means payments has not seen the order yet.
    resume
      .mockRejectedValueOnce(new Error('404'))
      .mockRejectedValueOnce(new Error('404'))
      .mockResolvedValue({ id: 1, checkout_url: 'https://checkout.stripe.test/session' })

    await placeCardOrder()

    await waitFor(() => expect(assigned).toBe('https://checkout.stripe.test/session'), {
      timeout: 5000,
    })
    expect(resume).toHaveBeenCalledTimes(3)
  })

  it('falls back to the order page rather than spinning forever', async () => {
    // The order exists either way, and the order page already offers "Pay now".
    // An extra tap beats a spinner that never resolves.
    resume.mockRejectedValue(new Error('404'))

    await placeCardOrder()

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/orders/77'), { timeout: 9000 })
    expect(assigned).toBeNull()
  }, 12000)

  it('does not poll at all for a cash order', async () => {
    const user = userEvent.setup()
    render(
      <QueryProvider>
        <MemoryRouter>
          <CartPage />
        </MemoryRouter>
      </QueryProvider>,
    )
    await screen.findByText(/Pizza/)
    // COD is the default, so no tab click — straight to placing it.
    await user.click(screen.getByRole('button', { name: /place order \(cash on delivery\)/i }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/orders/77'))
    expect(resume).not.toHaveBeenCalled()
  })
})
