import { render as renderReact } from '@testing-library/react'
import { PermissionContext } from '../auth/permissions'
export * from '@testing-library/react'

// Existing operational unit tests explicitly render with full capabilities.
// AuthGate and inner PermissionProvider instances override this fixture.
export function render(ui: Parameters<typeof renderReact>[0], options?: Parameters<typeof renderReact>[1]) {
  return renderReact(<PermissionContext.Provider value={{ permissions: [], can: () => true, any: () => true }}>{ui}</PermissionContext.Provider>, options)
}
