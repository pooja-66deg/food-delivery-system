import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegisterPage } from '../../src/pages/RegisterPage'

/**
 * Registering as a restaurant, which is the one sign-up that does not end in a
 * session.
 *
 * The account is created inactive and stays that way until an operator approves
 * the venue, so the two things worth pinning down are that the business details
 * actually reach the API, and that the page does not try to log the applicant
 * in afterwards — an auto-login here would replace a clear "we're reviewing it"
 * with a bare 401 the applicant cannot interpret.
 */

// Typed with an explicit rest parameter: vi.fn(() => …) infers a zero-length
// tuple for its arguments, and `mock.calls[0][0]` then fails to type-check under
// `npm run build`, which compiles the tests as well as the app.
const register = vi.fn((..._args: unknown[]) => Promise.resolve({}))
const login = vi.fn((..._args: unknown[]) => Promise.resolve({}))
const saveSession = vi.fn(() => Promise.resolve())
const navigate = vi.fn()

vi.mock('../../src/auth/AuthContext', () => ({
  useAuth: () => ({ saveSession, user: null, setUser: () => {} }),
}))

vi.mock('../../src/api/auth', () => ({
  authApi: {
    register: (...args: unknown[]) => register(...args),
    login: (...args: unknown[]) => login(...args),
  },
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

function renderRegister() {
  render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  )
}

/** Fill the whole form on the Restaurant tab and submit it. */
async function submitRestaurantSignup() {
  renderRegister()
  await userEvent.click(screen.getByRole('button', { name: 'Restaurant' }))

  await userEvent.type(screen.getByLabelText('First name'), 'Alex')
  await userEvent.type(screen.getByLabelText('Last name'), 'Rivera')
  await userEvent.type(screen.getByLabelText('Email'), 'alex@example.com')
  await userEvent.type(screen.getByLabelText('Phone'), '+919876543210')
  await userEvent.type(screen.getByLabelText('Password'), 'supersecret1')

  await userEvent.type(screen.getByLabelText('Restaurant name'), 'Spice Garden')
  await userEvent.type(screen.getByLabelText('Address'), '12 Residency Road')
  await userEvent.type(screen.getByLabelText('City'), 'Bengaluru')
  await userEvent.type(screen.getByLabelText('Restaurant phone'), '+919876500001')
  await userEvent.selectOptions(screen.getByLabelText('Food type'), 'veg')

  await userEvent.click(screen.getByRole('button', { name: 'Submit for approval' }))
}

beforeEach(() => {
  register.mockClear()
  login.mockClear()
  saveSession.mockClear()
  navigate.mockClear()
})

describe('registering a restaurant', () => {
  it('does not ask a customer for business details', async () => {
    renderRegister()
    expect(screen.queryByLabelText('Restaurant name')).toBeNull()
  })

  it('asks for them on the restaurant tab', async () => {
    renderRegister()
    await userEvent.click(screen.getByRole('button', { name: 'Restaurant' }))

    expect(screen.getByLabelText('Restaurant name')).toBeInTheDocument()
    expect(screen.getByLabelText('Food type')).toBeInTheDocument()
  })

  it('sends the venue alongside the account', async () => {
    await submitRestaurantSignup()

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1))
    const payload = register.mock.calls[0][0] as Record<string, unknown>
    const venue = payload.restaurant as Record<string, unknown>

    expect(payload.role).toBe('restaurant')
    expect(venue.name).toBe('Spice Garden')
    expect(venue.city).toBe('Bengaluru')
    expect(venue.food_type).toBe('veg')
  })

  it('sends the venue phone separately from the owner phone', async () => {
    await submitRestaurantSignup()

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1))
    const payload = register.mock.calls[0][0] as Record<string, unknown>
    const venue = payload.restaurant as Record<string, unknown>

    expect(payload.phone).toBe('+919876543210')
    expect(venue.phone).toBe('+919876500001')
  })

  it('sends an omitted cuisine as null rather than an empty string', async () => {
    await submitRestaurantSignup()

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1))
    const payload = register.mock.calls[0][0] as Record<string, unknown>
    expect((payload.restaurant as Record<string, unknown>).cuisine).toBeNull()
  })

  it('does not try to log the applicant in', async () => {
    await submitRestaurantSignup()

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1))
    expect(login).not.toHaveBeenCalled()
    expect(saveSession).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('explains what happens next instead', async () => {
    await submitRestaurantSignup()

    expect(await screen.findByText('Registration received')).toBeInTheDocument()
    expect(screen.getByText(/Spice Garden/)).toBeInTheDocument()
    expect(screen.getByText(/alex@example.com/)).toBeInTheDocument()
  })

  it('still logs a customer straight in', async () => {
    renderRegister()
    await userEvent.type(screen.getByLabelText('First name'), 'Cara')
    await userEvent.type(screen.getByLabelText('Last name'), 'Customer')
    await userEvent.type(screen.getByLabelText('Email'), 'cara@example.com')
    await userEvent.type(screen.getByLabelText('Phone'), '+919876543210')
    await userEvent.type(screen.getByLabelText('Password'), 'supersecret1')

    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
    const payload = register.mock.calls[0][0] as Record<string, unknown>
    expect(payload.restaurant).toBeUndefined()
  })
})
