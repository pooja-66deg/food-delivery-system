import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { RegisterPage } from '../../src/pages/RegisterPage'

vi.mock('../../src/auth/AuthContext', () => ({
  useAuth: () => ({ saveSession: () => Promise.resolve(), user: null, setUser: () => {} }),
}))

vi.mock('../../src/api/auth', () => ({
  authApi: { register: () => Promise.resolve({}), login: () => Promise.resolve({}) },
}))

function renderRegister() {
  render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  )
}

describe('RegisterPage input filtering', () => {
  it('strips digits typed into the first name', async () => {
    renderRegister()
    const input = screen.getByLabelText('First name')

    await userEvent.type(input, 'Alex1')

    expect(input).toHaveValue('Alex')
  })

  it('strips special characters typed into the last name', async () => {
    renderRegister()
    const input = screen.getByLabelText('Last name')

    await userEvent.type(input, 'R2D2!')

    expect(input).toHaveValue('RD')
  })

  it('keeps spaces in names', async () => {
    renderRegister()
    const input = screen.getByLabelText('First name')

    await userEvent.type(input, 'Mary Jane')

    expect(input).toHaveValue('Mary Jane')
  })

  it('rejects letters typed into the phone', async () => {
    renderRegister()
    const input = screen.getByLabelText('Phone')

    await userEvent.type(input, '55512ab345')

    expect(input).toHaveValue('55512345')
  })

  it('keeps a leading plus on the phone', async () => {
    renderRegister()
    const input = screen.getByLabelText('Phone')

    await userEvent.type(input, '+15550002222')

    expect(input).toHaveValue('+15550002222')
  })

  it('applies the same rules on the restaurant and driver tabs', async () => {
    renderRegister()

    await userEvent.click(screen.getByRole('button', { name: 'Driver' }))
    await userEvent.type(screen.getByLabelText('First name'), 'Alex9')

    expect(screen.getByLabelText('First name')).toHaveValue('Alex')
  })
})
