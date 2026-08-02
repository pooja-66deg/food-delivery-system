
import { filterPhoneInput } from './inputFilters'

export const DEFAULT_COUNTRY_CODE = '91' // India

const SEPARATORS = /[\s()\-./]/g
const DIGITS_ONLY = /^\d+$/

const MIN_DIGITS = 8
export const MAX_DIGITS = 15

export const NATIONAL_DIGITS = 10 // Indian mobile numbers, sans country code

export const PHONE_ERROR =
  'Enter a valid phone number — 10 digits for India, or +<country code> followed by the national number'

/** Return the number in E.164 form, or null if it isn't a usable number. */
export function normalizePhone(value: string): string | null {
  let compact = value.trim().replace(SEPARATORS, '')

  // "00" is the international dialling prefix across most of the world.
  if (compact.startsWith('00')) compact = `+${compact.slice(2)}`

  if (compact.startsWith('+')) {
    const digits = compact.slice(1)
    if (!DIGITS_ONLY.test(digits) || digits.length < MIN_DIGITS || digits.length > MAX_DIGITS) {
      return null
    }
    return `+${digits}`
  }

  if (!DIGITS_ONLY.test(compact)) return null

  const national = compact.replace(/^0+/, '')

  // Already country-coded but missing the "+", e.g. "919876543210".
  if (
    national.startsWith(DEFAULT_COUNTRY_CODE) &&
    national.length === DEFAULT_COUNTRY_CODE.length + NATIONAL_DIGITS
  ) {
    return `+${national}`
  }

  if (national.length !== NATIONAL_DIGITS) return null
  return `+${DEFAULT_COUNTRY_CODE}${national}`
}

/** Validation message for a number, or null when it's fine. */
export function phoneError(value: string): string | null {
  return normalizePhone(value) === null ? PHONE_ERROR : null
}

export function clampPhoneInput(value: string): string {
  const filtered = filterPhoneInput(value)

  if (filtered.startsWith('+')) return `+${filtered.slice(1, 1 + MAX_DIGITS)}`
  if (filtered.length <= NATIONAL_DIGITS) return filtered

  return normalizePhone(filtered) ?? filtered.slice(0, NATIONAL_DIGITS)
}
