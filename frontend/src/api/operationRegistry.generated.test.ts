import { describe, expect, it } from 'vitest'

import { operationRegistry } from './operationRegistry.generated'

describe('generated operation registry', () => {
  it('maps schema methods and paths to stable operation ids', () => {
    expect(operationRegistry['GET /me/dashboard']).toBe('get_dashboard_me_dashboard_get')
    expect(operationRegistry['POST /auth/refresh']).toBe('refresh_auth_refresh_post')
    expect(Object.keys(operationRegistry)).toHaveLength(38)
  })
})
