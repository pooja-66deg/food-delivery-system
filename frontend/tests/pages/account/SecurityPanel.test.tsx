import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SecurityPanel } from '../../../src/pages/account/SecurityPanel'

const mocks = vi.hoisted(() => ({
  changePassword: vi.fn(),
  replaceTokens: vi.fn(),
}))

vi.mock('../../../src/auth/AuthContext', () => ({
  useAuth: () => ({ replaceTokens: mocks.replaceTokens }),
}))

vi.mock('../../../src/api/auth', () => ({
  authApi: { changePassword: mocks.changePassword },
}))

const TOKENS = { access_token: 'new-access', refresh_token: 'new-refresh' }

async function fill(current: string, next: string, confirm: string) {
  await userEvent.type(screen.getByLabelText('Current password'), current)
  await userEvent.type(screen.getByLabelText('New password'), next)
  await userEvent.type(screen.getByLabelText('Confirm new password'), confirm)
  await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
}

beforeEach(() => {
  mocks.changePassword.mockReset().mockResolvedValue(TOKENS)
  mocks.replaceTokens.mockReset()
})

describe('SecurityPanel', () => {
  it('masks all three fields by default', () => {
    render(<SecurityPanel />)

    for (const label of ['Current password', 'New password', 'Confirm new password']) {
      expect(screen.getByLabelText(label)).toHaveAttribute('type', 'password')
    }
  })

  it('refuses to submit when the confirmation does not match', async () => {
    render(<SecurityPanel />)

    await fill('oldpassword1', 'newpassword1', 'newpassword2')

    expect(mocks.changePassword).not.toHaveBeenCalled()
    expect(screen.getByText(/do not match/i)).toBeInTheDocument()
  })

  it('sends the change and stores the replacement tokens', async () => {
    // The change invalidates the token this tab holds, so failing to store the
    // returned pair would sign the user out of their own session.
    render(<SecurityPanel />)

    await fill('oldpassword1', 'newpassword1', 'newpassword1')

    await waitFor(() => expect(mocks.changePassword).toHaveBeenCalledWith('oldpassword1', 'newpassword1'))
    expect(mocks.replaceTokens).toHaveBeenCalledWith(TOKENS)
  })

  it('clears the fields and confirms once the change lands', async () => {
    render(<SecurityPanel />)

    await fill('oldpassword1', 'newpassword1', 'newpassword1')

    await waitFor(() => expect(screen.getByText(/password changed/i)).toBeInTheDocument())
    expect(screen.getByLabelText('Current password')).toHaveValue('')
  })

  it('surfaces a rejected current password without clearing the form', async () => {
    mocks.changePassword.mockRejectedValue(new Error('nope'))
    render(<SecurityPanel />)

    await fill('wrongpassword', 'newpassword1', 'newpassword1')

    await waitFor(() => expect(screen.getByText(/could not change password/i)).toBeInTheDocument())
    expect(mocks.replaceTokens).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Current password')).toHaveValue('wrongpassword')
  })
})
