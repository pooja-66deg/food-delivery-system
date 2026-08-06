import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Modal } from '../../src/components/ui'

const onClose = vi.fn()

function renderModal(open = true) {
  onClose.mockReset()
  return render(
    <Modal open={open} title="Add a restaurant" subtitle="Fill this in" onClose={onClose}>
      <button type="button">Inside</button>
    </Modal>,
  )
}

describe('Modal', () => {
  it('renders nothing while closed', () => {
    renderModal(false)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows its title, subtitle and content when open', () => {
    renderModal()

    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('heading', { name: 'Add a restaurant' })).toBeInTheDocument()
    expect(screen.getByText('Fill this in')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Inside' })).toBeInTheDocument()
  })

  it('closes on the close button', async () => {
    renderModal()

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalled()
  })

  it('closes on Escape', async () => {
    renderModal()

    await userEvent.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalled()
  })

  it('a click inside the panel is not a dismiss', async () => {
    renderModal()

    await userEvent.click(screen.getByRole('button', { name: 'Inside' }))

    expect(onClose).not.toHaveBeenCalled()
  })

  it('locks the page behind it from scrolling, and restores it on close', () => {
    const { unmount } = renderModal()
    expect(document.body.style.overflow).toBe('hidden')

    unmount()

    expect(document.body.style.overflow).not.toBe('hidden')
  })
})
