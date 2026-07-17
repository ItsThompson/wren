import type { UserConfig } from 'vite'

const BACKEND_TARGET = 'http://localhost:8000'

const backendProxy = {
  target: BACKEND_TARGET,
  changeOrigin: true,
}

/**
 * Same-origin API proxy for `npm run dev`. Only the routes the SPA itself calls
 * same-origin are proxied. The OAuth AS/agent endpoints (`/token`, `/revoke`,
 * `/register`, `/jwks`, `/.well-known`, `/skill`) are not here: the MCP Inspector
 * hits those on the backend `:8000` directly via dev CORS, not through this proxy.
 * Keep `/authorize` local because it is also a SPA route; only the consent API
 * subpaths are proxied.
 */
export const devServerProxy = {
  '^/auth(?:/|$)': backendProxy,
  '/authorize/context': backendProxy,
  '/authorize/decision': backendProxy,
  '/roadmaps': backendProxy,
  '/me': backendProxy,
  '/users': backendProxy,
} satisfies NonNullable<NonNullable<UserConfig['server']>['proxy']>
