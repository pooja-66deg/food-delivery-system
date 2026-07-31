import { describe, expect, it } from 'vitest'

import { filterNameInput, filterPhoneInput } from '../../src/lib/inputFilters'

// These filters must mirror _NAME_RE / _PHONE_RE in src/modules/users/schemas.py
// so the browser never lets through anything the API would reject with a 422.

describe('filterNameInput', () => {
  it('strips digits', () => {
    expect(filterNameInput('Alex1')).toBe('Alex')
  })

  it('strips special characters', () => {
    expect(filterNameInput('Al@x')).toBe('Alx')
  })

  it('keeps spaces so multi-word names still work', () => {
    expect(filterNameInput('Mary Jane')).toBe('Mary Jane')
  })

  it('preserves letter case', () => {
    expect(filterNameInput('McDonald')).toBe('McDonald')
  })

  it('strips digits and punctuation from mixed input', () => {
    expect(filterNameInput('R2D2!')).toBe('RD')
  })
})

describe('filterPhoneInput', () => {
  it('strips letters', () => {
    expect(filterPhoneInput('55512ab345')).toBe('55512345')
  })

  it('keeps a leading plus', () => {
    expect(filterPhoneInput('+15550002222')).toBe('+15550002222')
  })

  it('strips a plus that is not leading', () => {
    expect(filterPhoneInput('555+123')).toBe('555123')
  })

  it('strips spaces and punctuation', () => {
    expect(filterPhoneInput('555 123 4567!')).toBe('5551234567')
  })

  it('reduces a non-numeric entry to an empty string', () => {
    expect(filterPhoneInput('call-me')).toBe('')
  })
})
