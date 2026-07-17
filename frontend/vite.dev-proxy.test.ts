import { describe, expect, it } from 'vitest'

import { devServerProxy } from './vite.dev-proxy.ts'

const isProxiedByDevServer = (path: string): boolean =>
  Object.keys(devServerProxy).some((context) => {
    if (context.startsWith('^')) return new RegExp(context).test(path)
    return path.startsWith(context)
  })

describe('devServerProxy', () => {
  it('proxies account API routes without capturing the OAuth consent SPA route', () => {
    expect(isProxiedByDevServer('/auth/login')).toBe(true)
    expect(isProxiedByDevServer('/auth/register')).toBe(true)
    expect(isProxiedByDevServer('/authorize?auth_request_id=request-1')).toBe(false)
    expect(isProxiedByDevServer('/authorize')).toBe(false)
  })

  it('proxies only the consent API subpaths under authorize', () => {
    expect(isProxiedByDevServer('/authorize/context?auth_request_id=request-1')).toBe(true)
    expect(isProxiedByDevServer('/authorize/decision')).toBe(true)
  })

  it('does not proxy OAuth AS/agent endpoints the MCP Inspector hits directly', () => {
    expect(isProxiedByDevServer('/token')).toBe(false)
    expect(isProxiedByDevServer('/revoke')).toBe(false)
    expect(isProxiedByDevServer('/register')).toBe(false)
    expect(isProxiedByDevServer('/jwks')).toBe(false)
    expect(isProxiedByDevServer('/.well-known/oauth-authorization-server')).toBe(false)
    expect(isProxiedByDevServer('/skill')).toBe(false)
  })
})
