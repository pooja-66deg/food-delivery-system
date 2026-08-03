import { useState } from 'react'
import type { FormEvent } from 'react'
import { PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'

import { Alert, Button } from '../components/ui'

interface CardPaymentStepProps {
  /** Called once Stripe reports the payment as succeeded or processing. */
  onPaid: () => void
  onCancel?: () => void
}

/**
 * Collects the card and confirms the PaymentIntent the surrounding
 * `StripeElements` was created with.
 *
 * The order is only marked paid by the webhook — this component reports what
 * the browser saw, which is why an interrupted confirmation still leaves the
 * order payable rather than lost.
 */
export function CardPaymentStep({ onPaid, onCancel }: CardPaymentStepProps) {
  const stripe = useStripe()
  const elements = useElements()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return

    setBusy(true)
    setError(null)
    try {
      const result = await stripe.confirmPayment({
        elements,
        // Stay on the page unless the card demands a redirect (3-D Secure).
        redirect: 'if_required',
      })
      if (result.error) {
        setError(result.error.message ?? 'The card could not be charged.')
        return
      }
      const status = result.paymentIntent?.status
      if (status === 'succeeded' || status === 'processing') {
        onPaid()
        return
      }
      setError('The payment was not completed. You can try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form-stack" onSubmit={submit}>
      <PaymentElement />
      {error && <Alert>{error}</Alert>}
      <Button type="submit" block loading={busy} disabled={!stripe}>
        Pay now
      </Button>
      {onCancel && (
        <Button type="button" variant="ghost" block onClick={onCancel}>
          Pay later
        </Button>
      )}
    </form>
  )
}
