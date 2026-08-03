/**
 * The Stripe publishable key, or null when the app is running without Stripe.
 *
 * Everything card-related keys off this: with no key the card option is not
 * offered at all, so the app stays usable with no payment configuration.
 */
export function publishableKey(): string | null {
  const key = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY as string | undefined
  return key && key.trim() !== '' ? key : null
}
