import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CardPaymentStep } from '../../src/payments/CardPaymentStep'

const mocks = vi.hoisted(() => ({
  confirmPayment: vi.fn(),
  stripe: null as unknown,
  elements: {} as unknown,
}))

// Stripe's card element renders in a cross-origin iframe no test can drive, so
// the library is mocked and what is asserted is OUR wiring around it.
vi.mock('@stripe/react-stripe-js', () => ({
  PaymentElement: () => <div data-testid="payment-element" />,
  useStripe: () => mocks.stripe,
  useElements: () => mocks.elements,
}))

beforeEach(() => {
  mocks.confirmPayment.mockReset().mockResolvedValue({ paymentIntent: { status: 'succeeded' } })
  mocks.stripe = { confirmPayment: mocks.confirmPayment }
  mocks.elements = { some: 'elements' }
})

describe('CardPaymentStep', () => {
  it('renders the card element', () => {
    render(<CardPaymentStep onPaid={() => {}} />)

    expect(screen.getByTestId('payment-element')).toBeInTheDocument()
  })

  it('confirms without navigating away unless the card demands it', async () => {
    render(<CardPaymentStep onPaid={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    await waitFor(() => expect(mocks.confirmPayment).toHaveBeenCalled())
    expect(mocks.confirmPayment.mock.calls[0][0]).toMatchObject({
      elements: mocks.elements,
      redirect: 'if_required',
    })
  })

  it('reports success to the caller', async () => {
    const onPaid = vi.fn()
    render(<CardPaymentStep onPaid={onPaid} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    await waitFor(() => expect(onPaid).toHaveBeenCalledTimes(1))
  })

  it('treats a processing intent as paid', async () => {
    // The webhook settles it; blocking the customer here would be a dead end.
    mocks.confirmPayment.mockResolvedValue({ paymentIntent: { status: 'processing' } })
    const onPaid = vi.fn()
    render(<CardPaymentStep onPaid={onPaid} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    await waitFor(() => expect(onPaid).toHaveBeenCalled())
  })

  it('shows the decline message and stays put', async () => {
    mocks.confirmPayment.mockResolvedValue({ error: { message: 'Your card was declined.' } })
    const onPaid = vi.fn()
    render(<CardPaymentStep onPaid={onPaid} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    expect(await screen.findByText('Your card was declined.')).toBeInTheDocument()
    expect(onPaid).not.toHaveBeenCalled()
  })

  it('does not claim success for an unfinished intent', async () => {
    mocks.confirmPayment.mockResolvedValue({ paymentIntent: { status: 'requires_payment_method' } })
    const onPaid = vi.fn()
    render(<CardPaymentStep onPaid={onPaid} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pay now' }))

    expect(await screen.findByText(/was not completed/i)).toBeInTheDocument()
    expect(onPaid).not.toHaveBeenCalled()
  })

  it('stays disabled until Stripe has loaded', () => {
    mocks.stripe = null
    render(<CardPaymentStep onPaid={() => {}} />)

    expect(screen.getByRole('button', { name: 'Pay now' })).toBeDisabled()
  })

  it('offers a way out that is not a payment', async () => {
    const onCancel = vi.fn()
    render(<CardPaymentStep onPaid={() => {}} onCancel={onCancel} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pay later' }))

    expect(onCancel).toHaveBeenCalled()
    expect(mocks.confirmPayment).not.toHaveBeenCalled()
  })
})
