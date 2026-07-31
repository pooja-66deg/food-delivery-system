import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LoginPage } from '../../src/pages/LoginPage'
import { RegisterPage } from '../../src/pages/RegisterPage'
import { ResetPasswordPage } from '../../src/pages/ResetPasswordPage'

// Every page that asks for a password must offer the reveal toggle, so people
// can check what they typed before submitting.

vi.mock('../../src/auth/AuthContext', () => ({
  useAuth: () => ({ saveSession: () => Promise.resolve(), user: null, setUser: () => {} }),
}))

vi.mock('../../src/api/auth', () => ({
  authApi: {
    login: () => Promise.resolve({}),
    register: () => Promise.resolve({}),
    resetPassword: () => Promise.resolve({}),
  },
}))

const pages = [
  ['sign in', <LoginPage key="login" />],
  ['register', <RegisterPage key="register" />],
  ['reset password', <ResetPasswordPage key="reset" />],
] as const

describe('password reveal toggle', () => {
  it.each(pages)('is offered on the %s page', (_name, element) => {
    render(<MemoryRouter>{element}</MemoryRouter>)

    expect(screen.getByRole('button', { name: /show password/i })).toBeInTheDocument()
  })

  it.each(pages)('reveals the password field on the %s page', async (_name, element) => {
    render(<MemoryRouter>{element}</MemoryRouter>)
    const toggle = screen.getByRole('button', { name: /show password/i })

    await userEvent.click(toggle)

    expect(screen.getByRole('button', { name: /hide password/i })).toBeInTheDocument()
  })
})
