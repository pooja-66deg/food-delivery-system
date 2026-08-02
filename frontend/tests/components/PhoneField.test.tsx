import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { PhoneField } from '../../src/components/ui'

/** PhoneField is controlled, so exercise it the way the pages drive it. */
function Harness({ initial = '' }: { initial?: string }) {
  const [phone, setPhone] = useState(initial)
  return <PhoneField label="Phone" name="phone" value={phone} onChange={setPhone} />
}

describe('PhoneField', () => {
  it('shows the default country code before anything is typed', () => {
    render(<Harness />)

    expect(screen.getByText('+91')).toBeInTheDocument()
  })

  it('keeps showing it for a plain national number', async () => {
    render(<Harness />)

    await userEvent.type(screen.getByLabelText('Phone'), '9876543210')

    expect(screen.getByText('+91')).toBeInTheDocument()
  })

  it('drops it once the number carries its own country code', async () => {
    render(<Harness />)

    await userEvent.type(screen.getByLabelText('Phone'), '+1')

    expect(screen.queryByText('+91')).not.toBeInTheDocument()
  })

  it('keeps typing intact across the prefix disappearing', async () => {
    // The prefix toggles mid-word; if that remounted the input, the characters
    // typed after the "+" would land somewhere else or be dropped entirely.
    render(<Harness />)

    await userEvent.type(screen.getByLabelText('Phone'), '+15550002222')

    expect(screen.getByLabelText('Phone')).toHaveValue('+15550002222')
  })

  it('keeps focus while the prefix toggles', async () => {
    render(<Harness />)
    const input = screen.getByLabelText('Phone')

    await userEvent.type(input, '+1')

    expect(input).toHaveFocus()
  })

  it('brings the prefix back if the country code is deleted', async () => {
    render(<Harness initial="+1555" />)

    await userEvent.clear(screen.getByLabelText('Phone'))

    expect(screen.getByText('+91')).toBeInTheDocument()
  })

  it('filters characters that could never be part of a number', async () => {
    render(<Harness />)

    await userEvent.type(screen.getByLabelText('Phone'), '98765ab43210')

    expect(screen.getByLabelText('Phone')).toHaveValue('9876543210')
  })

  it('stops accepting digits once the number is complete', async () => {
    render(<Harness />)
    const input = screen.getByLabelText('Phone')

    await userEvent.type(input, '98765432109999')

    expect(input).toHaveValue('9876543210')
  })

  it('lets a number with its own country code run longer', async () => {
    render(<Harness />)
    const input = screen.getByLabelText('Phone')

    await userEvent.type(input, '+442079460958')

    expect(input).toHaveValue('+442079460958')
  })

  it('points the input at the prefix for screen readers', () => {
    render(<Harness />)

    const describedBy = screen.getByLabelText('Phone').getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(describedBy as string)).toHaveTextContent('+91')
  })
})
