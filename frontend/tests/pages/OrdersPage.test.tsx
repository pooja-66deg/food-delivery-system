import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OrdersPage } from '../../src/pages/OrdersPage'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  resumePayment: vi.fn(),
}))

vi.mock('../../src/api/orders', () => ({ ordersApi: mocks }))

// The card step needs Stripe context; the wiring is covered by its own test.
vi.mock('../../src/payments/StripeElements', () => ({
  StripeElements: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../src/payments/CardPaymentStep', () => ({
  CardPaymentStep: () => <div>card step</div>,
}))

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    restaurant_id: 1,
    status: 'PREPARING',
    total: 20,
    created_at: '2026-08-01T10:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OrdersPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue([order()])
  mocks.resumePayment.mockReset().mockResolvedValue({ client_secret: 'pi_secret' })
})

describe('OrdersPage tabs', () => {
  it('opens on the active orders', async () => {
    renderPage()

    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith('active'))
    expect(await screen.findByText('Order #1')).toBeInTheDocument()
  })

  it('asks for past orders when that tab is chosen', async () => {
    renderPage()
    await screen.findByText('Order #1')

    await userEvent.click(screen.getByRole('tab', { name: 'Past' }))

    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith('past'))
  })

  it('marks the chosen tab as selected', async () => {
    renderPage()
    await screen.findByText('Order #1')

    await userEvent.click(screen.getByRole('tab', { name: 'Past' }))

    expect(screen.getByRole('tab', { name: 'Past' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Active' })).toHaveAttribute('aria-selected', 'false')
  })

  it('gives each empty tab its own wording', async () => {
    mocks.list.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText(/nothing on the way/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Past' }))

    expect(await screen.findByText(/no completed orders/i)).toBeInTheDocument()
  })
})

describe('OrdersPage payment', () => {
  it('offers Pay now only on an unpaid order', async () => {
    mocks.list.mockResolvedValue([order({ id: 1, status: 'PAYMENT_PENDING' }), order({ id: 2 })])
    renderPage()

    await screen.findByText('Order #1')
    expect(screen.getAllByRole('button', { name: 'Pay now' })).toHaveLength(1)
  })

  it('reopens the card step with a fresh secret', async () => {
    // The checkout secret is never stored, so this must come from the server.
    mocks.list.mockResolvedValue([order({ status: 'PAYMENT_PENDING' })])
    renderPage()
    await screen.findByText('Order #1')

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    await waitFor(() => expect(mocks.resumePayment).toHaveBeenCalledWith(1))
    expect(await screen.findByText('card step')).toBeInTheDocument()
  })

  it('explains when the order can no longer be paid online', async () => {
    mocks.list.mockResolvedValue([order({ status: 'PAYMENT_PENDING' })])
    mocks.resumePayment.mockResolvedValue({ client_secret: null })
    renderPage()
    await screen.findByText('Order #1')

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    expect(await screen.findByText(/no longer be paid for online/i)).toBeInTheDocument()
  })

  it('surfaces a failure to reopen payment', async () => {
    mocks.list.mockResolvedValue([order({ status: 'PAYMENT_PENDING' })])
    mocks.resumePayment.mockRejectedValue(new Error('offline'))
    renderPage()
    await screen.findByText('Order #1')

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    expect(await screen.findByText(/could not reopen payment/i)).toBeInTheDocument()
  })
})
