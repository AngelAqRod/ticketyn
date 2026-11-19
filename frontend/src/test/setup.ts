import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Routes are lazy chunks: the first import() of each page is transformed on demand, which takes longer than the 1 s default.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
