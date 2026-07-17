import { describe, expect, it } from 'vitest'

import { devServerProxy } from './vite.dev-proxy.ts'

describe('vite dev proxy', () => {
  it('proxies same-origin auth requests to the external backend', () => {
    expect(devServerProxy).toMatchObject({
      '^/auth(?:/|$)': { target: 'http://localhost:8000', changeOrigin: true },
    })
  })

  it('keeps the SPA consent route local while proxying consent API calls', () => {
    expect(devServerProxy).not.toHaveProperty('/authorize')
    expect(devServerProxy).toHaveProperty('/authorize/context')
    expect(devServerProxy).toHaveProperty('/authorize/decision')
  })
})
