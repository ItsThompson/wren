import type { ReactElement } from 'react'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'

import { createHookWrapper, type HookWrapperOptions } from './createHookWrapper'
import { TEST_API_BASE } from './test-api-base'

/** Re-exported so existing harness consumers keep a single import site. */
export { TEST_API_BASE }

export interface ProviderRenderOptions
  extends Omit<RenderOptions, 'wrapper'>,
    HookWrapperOptions {}

/**
 * Render `ui` under a fresh SWR cache + the shared API clients + an auth layer +
 * a router, wired the same way production is, so cache does not leak across tests
 * and hooks resolve the same clients as the app.
 *
 * The provider stack itself lives in {@link createHookWrapper} (single source for
 * both `render` and `renderHook`); this wraps it in `@testing-library/react`'s
 * `render` and forwards any remaining `RenderOptions` (e.g. `container`).
 */
export function renderWithProviders(
  ui: ReactElement,
  options: ProviderRenderOptions = {},
): RenderResult {
  const { baseUrl, initialEntries, authValue, useRealAuth, ...renderOptions } = options

  return render(ui, {
    wrapper: createHookWrapper({ baseUrl, initialEntries, authValue, useRealAuth }),
    ...renderOptions,
  })
}
