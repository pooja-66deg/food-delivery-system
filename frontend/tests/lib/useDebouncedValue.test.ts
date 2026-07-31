import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDebouncedValue } from '../../src/lib/useDebouncedValue'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

function renderDebounced(initial: string, delay = 250) {
  return renderHook(({ value }) => useDebouncedValue(value, delay), {
    initialProps: { value: initial },
  })
}

describe('useDebouncedValue', () => {
  it('returns the initial value immediately', () => {
    const { result } = renderDebounced('pizza')

    expect(result.current).toBe('pizza')
  })

  it('holds the previous value until the delay elapses', () => {
    const { result, rerender } = renderDebounced('p')

    rerender({ value: 'pi' })
    act(() => {
      vi.advanceTimersByTime(249)
    })

    expect(result.current).toBe('p')
  })

  it('publishes the new value once the delay elapses', () => {
    const { result, rerender } = renderDebounced('p')

    rerender({ value: 'pi' })
    act(() => {
      vi.advanceTimersByTime(250)
    })

    expect(result.current).toBe('pi')
  })

  it('publishes only the final value when typing quickly', () => {
    const { result, rerender } = renderDebounced('p')

    rerender({ value: 'pi' })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    rerender({ value: 'piz' })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    rerender({ value: 'pizz' })
    act(() => {
      vi.advanceTimersByTime(250)
    })

    expect(result.current).toBe('pizz')
  })

  it('cancels a pending update when the value reverts', () => {
    const { result, rerender } = renderDebounced('p')

    rerender({ value: 'pi' })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    rerender({ value: 'p' })
    act(() => {
      vi.advanceTimersByTime(250)
    })

    expect(result.current).toBe('p')
  })
})
