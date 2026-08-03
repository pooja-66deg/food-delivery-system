import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { Elements } from '@stripe/react-stripe-js'

import { Alert } from '../components/ui'
import { publishableKey } from './publishableKey'

// loadStripe injects a script tag, so it is called once per key rather than per
// render.
const cache = new Map<string, Promise<Stripe | null>>()

function stripeFor(key: string): Promise<Stripe | null> {
  const existing = cache.get(key)
  if (existing) return existing
  const created = loadStripe(key)
  cache.set(key, created)
  return created
}

/**
 * Stripe context for one payment. The client secret ties the Elements instance
 * to a specific PaymentIntent, so this must be remounted for a new one.
 */
export function StripeElements({
  clientSecret,
  children,
}: {
  clientSecret: string
  children: ReactNode
}) {
  const key = publishableKey()
  const stripe = useMemo(() => (key ? stripeFor(key) : null), [key])

  if (!stripe) {
    return <Alert>Card payments are not configured for this environment.</Alert>
  }

  return (
    <Elements stripe={stripe} options={{ clientSecret }}>
      {children}
    </Elements>
  )
}
