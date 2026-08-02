import { describe, expect, it } from 'vitest'

import { clampPhoneInput, normalizePhone, phoneError } from '../../src/lib/phone'

// These cases mirror tests/core/test_phone.py — the two implementations have to
// agree, or the browser accepts numbers the API rejects (or vice versa).

describe('normalizePhone', () => {
  it.each([
    ['9876543210', '+919876543210'],
    ['98765 43210', '+919876543210'],
    ['98765-43210', '+919876543210'],
    ['  9876543210  ', '+919876543210'],
    ['09876543210', '+919876543210'],
    ['+919876543210', '+919876543210'],
    ['+91 98765 43210', '+919876543210'],
    ['919876543210', '+919876543210'],
    ['0091 98765 43210', '+919876543210'],
    ['+1 555 000 0000', '+15550000000'],
    ['+44 20 7946 0958', '+442079460958'],
  ])('normalizes %s to %s', (raw, expected) => {
    expect(normalizePhone(raw)).toBe(expected)
  })

  it.each([
    '',
    'call-me',
    '55512ab345',
    '12345',
    '987654321',
    '98765432101',
    '+1',
    '+1234567890123456',
  ])('rejects %s', (raw) => {
    expect(normalizePhone(raw)).toBeNull()
  })

  it('resolves every spelling of one number to the same value', () => {
    const forms = ['9876543210', '098765 43210', '+91-98765-43210', '919876543210']
    expect(new Set(forms.map(normalizePhone)).size).toBe(1)
  })
})

describe('clampPhoneInput', () => {
  it('allows a full national number', () => {
    expect(clampPhoneInput('9876543210')).toBe('9876543210')
  })

  it('refuses an eleventh digit on the default country code', () => {
    expect(clampPhoneInput('98765432109')).toBe('9876543210')
  })

  it('allows E.164 room to breathe once a country code is typed', () => {
    expect(clampPhoneInput('+442079460958')).toBe('+442079460958')
  })

  it('stops at E.164 fifteen digits', () => {
    expect(clampPhoneInput('+1234567890123456789')).toBe('+123456789012345')
  })

  it('promotes an over-long paste rather than truncating it', () => {
    // Truncating "919876543210" to ten digits would silently register
    // "+919198765432" — a different person's number.
    expect(clampPhoneInput('919876543210')).toBe('+919876543210')
    expect(clampPhoneInput('09876543210')).toBe('+919876543210')
  })

  it('still strips characters a number can never contain', () => {
    expect(clampPhoneInput('98765ab432')).toBe('98765432')
  })
})

describe('phoneError', () => {
  it('is null for a usable number', () => {
    expect(phoneError('9876543210')).toBeNull()
  })

  it('explains the rule for an unusable one', () => {
    expect(phoneError('12345')).toContain('10 digits for India')
  })
})
