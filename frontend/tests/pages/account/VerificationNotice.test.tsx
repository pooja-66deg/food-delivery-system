import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { VerificationNotice } from '../../../src/pages/account/VerificationNotice'

const mocks = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  requestEmailVerification: vi.fn(),
}))

vi.mock('../../../src/auth/AuthContext', () => ({ useAuth: () => ({ user: mocks.user }) }))

vi.mock('../../../src/api/auth', () => ({
  authApi: { requestEmailVerification: mocks.requestEmailVerification },
}))

function signedIn(is_email_verified: boolean) {
  mocks.user = { id: 1, email: 'alex@example.com', role: 'customer', is_email_verified }
}

beforeEach(() => {
  mocks.user = null
  mocks.requestEmailVerification.mockReset().mockResolvedValue({ message: 'sent' })
})

describe('VerificationNotice', () => {
  it('shows a chip and no prompt once the address is verified', () => {
    signedIn(true)

    render(<VerificationNotice />)

    expect(screen.getByText('Email verified')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('prompts an unverified user with their address', () => {
    signedIn(false)

    render(<VerificationNotice />)

    expect(screen.getByRole('heading', { name: /verify your email/i })).toBeInTheDocument()
    expect(screen.getByText('alex@example.com')).toBeInTheDocument()
  })

  it('sends the verification email on request', async () => {
    signedIn(false)
    render(<VerificationNotice />)

    await userEvent.click(screen.getByRole('button', { name: /send verification email/i }))

    await waitFor(() => expect(mocks.requestEmailVerification).toHaveBeenCalledTimes(1))
    expect(screen.getByText(/link sent to alex@example.com/i)).toBeInTheDocument()
  })

  it('reports a failure to send', async () => {
    signedIn(false)
    mocks.requestEmailVerification.mockRejectedValue(new Error('nope'))
    render(<VerificationNotice />)

    await userEvent.click(screen.getByRole('button', { name: /send verification email/i }))

    await waitFor(() =>
      expect(screen.getByText(/could not send the verification email/i)).toBeInTheDocument(),
    )
  })

  it('renders nothing when signed out', () => {
    const { container } = render(<VerificationNotice />)

    expect(container).toBeEmptyDOMElement()
  })
})
