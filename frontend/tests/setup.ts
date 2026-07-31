// Adds jest-dom matchers (toBeInTheDocument, toHaveAttribute, …) to Vitest's
// expect, and clears the rendered tree between tests.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
