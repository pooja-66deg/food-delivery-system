import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../src/api/client'
import { NotificationPanel } from '../../../src/pages/account/NotificationPanel'

const mocks = vi.hoisted(() => ({
  preferences: vi.fn(),
  updatePreferences: vi.fn(),
}))

vi.mock('../../../src/api/notifications', () => ({ notificationsApi: mocks }))

const DEFAULTS = { email_enabled: true, sms_enabled: false, push_enabled: true }

const toggle = (name: string) => screen.getByRole('checkbox', { name: new RegExp(name) })

describe('NotificationPanel', () => {
  beforeEach(() => {
    mocks.preferences.mockReset()
    mocks.updatePreferences.mockReset()
    mocks.preferences.mockResolvedValue(DEFAULTS)
  })

  it('reflects the stored preferences', async () => {
    render(<NotificationPanel />)

    expect(await screen.findByRole('checkbox', { name: /Email/ })).toBeChecked()
    expect(toggle('Push')).toBeChecked()
    // SMS is opt-in, so it starts off.
    expect(toggle('SMS')).not.toBeChecked()
  })

  it('sends only the channel being changed', async () => {
    mocks.updatePreferences.mockResolvedValue({ ...DEFAULTS, sms_enabled: true })
    render(<NotificationPanel />)

    await userEvent.click(await screen.findByRole('checkbox', { name: /SMS/ }))

    await waitFor(() =>
      expect(mocks.updatePreferences).toHaveBeenCalledWith({ sms_enabled: true }),
    )
    expect(toggle('SMS')).toBeChecked()
  })

  it('turning a channel off sends false', async () => {
    mocks.updatePreferences.mockResolvedValue({ ...DEFAULTS, email_enabled: false })
    render(<NotificationPanel />)

    await userEvent.click(await screen.findByRole('checkbox', { name: /Email/ }))

    await waitFor(() =>
      expect(mocks.updatePreferences).toHaveBeenCalledWith({ email_enabled: false }),
    )
  })

  it('a rejected change snaps back instead of showing a state that was never stored', async () => {
    mocks.updatePreferences.mockRejectedValue(new ApiError('Nope', 500))
    render(<NotificationPanel />)

    await userEvent.click(await screen.findByRole('checkbox', { name: /SMS/ }))

    expect(await screen.findByText('Nope')).toBeInTheDocument()
    expect(toggle('SMS')).not.toBeChecked()
  })

  it('surfaces a load failure', async () => {
    mocks.preferences.mockRejectedValue(new ApiError('Service unavailable', 503))
    render(<NotificationPanel />)

    expect(await screen.findByText('Service unavailable')).toBeInTheDocument()
  })
})
