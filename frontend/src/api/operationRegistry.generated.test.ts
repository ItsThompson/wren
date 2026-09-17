import { describe, expect, it } from 'vitest'

import { operationDomainRegistry, operationRegistry } from './operationRegistry.generated'

describe('generated operation registry', () => {
  it('maps schema methods and paths to stable operation ids', () => {
    expect(operationRegistry['GET /me/dashboard']).toBe('get_dashboard_me_dashboard_get')
    expect(operationRegistry['POST /auth/refresh']).toBe('refresh_auth_refresh_post')
    expect(operationDomainRegistry['GET /me/dashboard']).toBe('accounts')
    expect(operationDomainRegistry['POST /roadmaps/{roadmap_id}/progress']).toBe('progress')
    expect(operationDomainRegistry['GET /skill']).toBe('skill')
    expect(new Set(Object.values(operationDomainRegistry))).toEqual(
      new Set(['accounts', 'oauth', 'roadmaps', 'progress', 'skill']),
    )
    expect(Object.keys(operationRegistry)).toHaveLength(38)
    expect(Object.keys(operationDomainRegistry)).toHaveLength(Object.keys(operationRegistry).length)
  })
})
