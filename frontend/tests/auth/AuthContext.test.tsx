import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, useAuth } from '../../src/auth/AuthContext'

const mocks = vi.hoisted(() => ({
  me: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('../../src/api/auth', () => ({ authApi: { me: mocks.me, logout: mocks.logout } }))

const USER = { id: 1, email: 'alex@example.com', role: 'customer', is_email_verified: true }

function Consumer() {
  const { isAuthenticated, logout } = useAuth()
  return (
    <>
      <span>{isAuthenticated ? 'signed in' : 'signed out'}</span>
      <button onClick={() => void logout()}>Sign out</button>
    </>
  )
}

async function signedIn() {
  localStorage.setItem('fd_access_token', 'access-token')
  localStorage.setItem('fd_refresh_token', 'refresh-token')
  render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>,
  )
  await screen.findByText('signed in')
}

beforeEach(() => {
  localStorage.clear()
  mocks.me.mockReset().mockResolvedValue(USER)
  mocks.logout.mockReset().mockResolvedValue(undefined)
})

describe('AuthContext logout', () => {
  it('revokes the session server-side before clearing storage', async () => {
    // Clearing localStorage alone leaves both tokens usable until they expire.
    await signedIn()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(mocks.logout).toHaveBeenCalledWith('refresh-token'))
    expect(localStorage.getItem('fd_access_token')).toBeNull()
    expect(localStorage.getItem('fd_refresh_token')).toBeNull()
    expect(screen.getByText('signed out')).toBeInTheDocument()
  })

  it('signs the user out even when the revoke call fails', async () => {
    // A network error must never strand someone in a session they tried to end.
    mocks.logout.mockRejectedValue(new Error('offline'))
    await signedIn()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument())
    expect(localStorage.getItem('fd_access_token')).toBeNull()
  })

  it('skips the call when there is no refresh token to revoke', async () => {
    localStorage.setItem('fd_access_token', 'access-token')
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )
    await screen.findByText('signed in')

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument())
    expect(mocks.logout).not.toHaveBeenCalled()
  })
})
