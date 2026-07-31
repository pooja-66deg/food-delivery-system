import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AccountPage } from '../../src/pages/AccountPage'

const mocks = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  setUser: () => {},
}))

vi.mock('../../src/auth/AuthContext', () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))

vi.mock('../../src/api/auth', () => ({
  authApi: {
    listAddresses: () => Promise.resolve([]),
    updateProfile: () => Promise.resolve(mocks.user),
    addAddress: () => Promise.resolve({}),
    deleteAddress: () => Promise.resolve(),
  },
}))

function signedInAs(role: string) {
  mocks.user = {
    id: 1,
    email: 'alex@example.com',
    phone: '15550001111',
    first_name: 'Alex',
    last_name: 'Rivera',
    role,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  }
}

beforeEach(() => {
  mocks.user = null
})

describe('AccountPage role awareness', () => {
  it.each([
    ['driver', 'Driver account'],
    ['customer', 'Customer account'],
    ['restaurant', 'Restaurant account'],
    ['admin', 'Admin account'],
  ])('labels a %s as "%s"', (role, expected) => {
    signedInAs(role)

    render(<AccountPage />)

    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('shows delivery addresses to a customer', () => {
    signedInAs('customer')

    render(<AccountPage />)

    expect(screen.getByRole('heading', { name: /delivery addresses/i })).toBeInTheDocument()
  })

  it.each(['driver', 'restaurant', 'admin'])('hides delivery addresses from a %s', (role) => {
    signedInAs(role)

    render(<AccountPage />)

    expect(screen.queryByRole('heading', { name: /delivery addresses/i })).not.toBeInTheDocument()
  })
})

describe('AccountPage profile form input filtering', () => {
  it('strips digits typed into the first name', async () => {
    signedInAs('customer')
    render(<AccountPage />)
    const input = screen.getByLabelText('First name')

    await userEvent.clear(input)
    await userEvent.type(input, 'Alex1')

    expect(input).toHaveValue('Alex')
  })

  it('strips special characters typed into the last name', async () => {
    signedInAs('customer')
    render(<AccountPage />)
    const input = screen.getByLabelText('Last name')

    await userEvent.clear(input)
    await userEvent.type(input, 'Rivera_')

    expect(input).toHaveValue('Rivera')
  })

  it('rejects non-numeric characters typed into the phone', async () => {
    signedInAs('customer')
    render(<AccountPage />)
    const input = screen.getByLabelText('Phone')

    await userEvent.clear(input)
    await userEvent.type(input, 'call-me')

    expect(input).toHaveValue('')
  })
})
