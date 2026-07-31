import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SearchSuggest } from '../../src/components/SearchSuggest'
import type { RestaurantSuggestion } from '../../src/api/restaurants'

const PIZZA: RestaurantSuggestion = { id: 1, name: 'Pizza Palace', city: 'Metropolis', cuisine: 'Italian' }
const PASTA: RestaurantSuggestion = { id: 2, name: 'Pasta Place', city: 'Metropolis', cuisine: 'Italian' }

// Defined once outside render so its identity is stable across rerenders.
const fetchTwo = () => Promise.resolve([PIZZA, PASTA])

function setup(overrides: Partial<Parameters<typeof SearchSuggest>[0]> = {}) {
  const onChange = vi.fn()
  const onSelect = vi.fn()
  const props = {
    value: '',
    onChange,
    onSelect,
    fetchSuggestions: fetchTwo,
    debounceMs: 0,
    ...overrides,
  }
  const view = render(<SearchSuggest {...props} />)
  return { onChange, onSelect, view }
}

async function openWith(term: string) {
  const bag = setup({ value: term })
  const input = screen.getByRole('combobox')
  // Focus it the way a user would — keyboard events go to the focused element,
  // so without this the arrow keys would land on document.body.
  await userEvent.click(input)
  await waitFor(() => expect(screen.queryByRole('listbox')).toBeInTheDocument())
  return { ...bag, input }
}

describe('SearchSuggest', () => {
  it('renders a combobox input', () => {
    setup()

    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('reports the input as collapsed before anything is typed', () => {
    setup()

    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
  })

  it('does not suggest for a single character', async () => {
    setup({ value: 'p' })

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
  })

  it('lists suggestions once two characters are entered', async () => {
    await openWith('pi')

    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      expect.stringContaining('Pizza Palace'),
      expect.stringContaining('Pasta Place'),
    ])
  })

  it('reports the input as expanded while suggestions are open', async () => {
    const { input } = await openWith('pi')

    expect(input).toHaveAttribute('aria-expanded', 'true')
  })

  it('labels each suggestion with its cuisine and city', async () => {
    await openWith('pi')

    expect(screen.getAllByRole('option')[0].textContent).toContain('Italian')
    expect(screen.getAllByRole('option')[0].textContent).toContain('Metropolis')
  })

  it('has no active option until an arrow key is pressed', async () => {
    const { input } = await openWith('pi')

    expect(input).not.toHaveAttribute('aria-activedescendant')
  })

  it('moves the active option down with ArrowDown', async () => {
    const { input } = await openWith('pi')

    await userEvent.keyboard('{ArrowDown}')

    expect(input).toHaveAttribute('aria-activedescendant', screen.getAllByRole('option')[0].id)
  })

  it('moves to the second option on a second ArrowDown', async () => {
    const { input } = await openWith('pi')

    await userEvent.keyboard('{ArrowDown}{ArrowDown}')

    expect(input).toHaveAttribute('aria-activedescendant', screen.getAllByRole('option')[1].id)
  })

  it('moves back up with ArrowUp', async () => {
    const { input } = await openWith('pi')

    await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowUp}')

    expect(input).toHaveAttribute('aria-activedescendant', screen.getAllByRole('option')[0].id)
  })

  it('marks the active option with aria-selected', async () => {
    await openWith('pi')

    await userEvent.keyboard('{ArrowDown}')

    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'false')
  })

  it('selects the active option on Enter', async () => {
    const { onSelect } = await openWith('pi')

    await userEvent.keyboard('{ArrowDown}{Enter}')

    expect(onSelect).toHaveBeenCalledWith(PIZZA)
  })

  it('does not select on Enter when no option is active', async () => {
    const { onSelect } = await openWith('pi')

    await userEvent.keyboard('{Enter}')

    expect(onSelect).not.toHaveBeenCalled()
  })

  it('selects a suggestion when it is clicked', async () => {
    const { onSelect } = await openWith('pi')

    await userEvent.click(screen.getAllByRole('option')[1])

    expect(onSelect).toHaveBeenCalledWith(PASTA)
  })

  it('closes the list on Escape', async () => {
    await openWith('pi')

    await userEvent.keyboard('{Escape}')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('keeps the typed text after Escape', async () => {
    const { input, onChange } = await openWith('pi')

    await userEvent.keyboard('{Escape}')

    expect(input).toHaveValue('pi')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('closes the list after a suggestion is chosen', async () => {
    await openWith('pi')

    await userEvent.click(screen.getAllByRole('option')[0])

    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
  })

  it('reports typing through onChange', async () => {
    const { onChange } = setup()

    await userEvent.type(screen.getByRole('combobox'), 'pi')

    expect(onChange).toHaveBeenCalled()
  })

  it('shows nothing when the fetch fails', async () => {
    const failing = () => Promise.reject(new Error('network down'))
    setup({ value: 'pi', fetchSuggestions: failing })

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
  })

  it('ignores a stale response that arrives after a newer one', async () => {
    // "pi" resolves slowly, "piz" quickly — the slow one must not overwrite.
    const slowThenFast = (q: string) =>
      new Promise<RestaurantSuggestion[]>((resolve) => {
        setTimeout(() => resolve(q === 'pi' ? [PASTA] : [PIZZA]), q === 'pi' ? 60 : 0)
      })

    const { view } = setup({ value: 'pi', fetchSuggestions: slowThenFast })
    view.rerender(
      <SearchSuggest
        value="piz"
        onChange={vi.fn()}
        onSelect={vi.fn()}
        fetchSuggestions={slowThenFast}
        debounceMs={0}
      />,
    )

    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(1))
    await new Promise((r) => setTimeout(r, 120))

    expect(screen.getAllByRole('option')[0].textContent).toContain('Pizza Palace')
  })
})
