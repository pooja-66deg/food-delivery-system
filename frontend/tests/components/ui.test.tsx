import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PasswordField } from '../../src/components/ui'

describe('PasswordField', () => {
  it('masks the value by default', () => {
    render(<PasswordField label="Password" name="password" />)

    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })

  it('reveals the value when the toggle is pressed', async () => {
    render(<PasswordField label="Password" name="password" />)

    await userEvent.click(screen.getByRole('button', { name: /show password/i }))

    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text')
  })

  it('masks the value again when the toggle is pressed twice', async () => {
    render(<PasswordField label="Password" name="password" />)

    await userEvent.click(screen.getByRole('button', { name: /show password/i }))
    await userEvent.click(screen.getByRole('button', { name: /hide password/i }))

    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })

  it('reports its state through aria-pressed', async () => {
    render(<PasswordField label="Password" name="password" />)

    const toggle = screen.getByRole('button', { name: /show password/i })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(toggle)

    expect(screen.getByRole('button', { name: /hide password/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('does not submit the surrounding form when toggled', async () => {
    const onSubmit = vi.fn((e: { preventDefault: () => void }) => e.preventDefault())
    render(
      <form onSubmit={onSubmit}>
        <PasswordField label="Password" name="password" />
      </form>,
    )

    await userEvent.click(screen.getByRole('button', { name: /show password/i }))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('forwards input attributes through to the underlying field', () => {
    render(<PasswordField label="Password" name="password" autoComplete="new-password" minLength={8} required />)

    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('autocomplete', 'new-password')
    expect(input).toHaveAttribute('minlength', '8')
    expect(input).toBeRequired()
  })
})
