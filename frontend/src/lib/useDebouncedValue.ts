import { useEffect, useState } from 'react'

/**
 * Returns `value` once it has stopped changing for `delayMs`.
 *
 * Used to keep the typeahead from firing a request per keystroke: each new
 * value cancels the pending timer, so only the value the user settles on is
 * published.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return settled
}
