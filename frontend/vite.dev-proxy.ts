import type { UserConfig } from 'vite'

const BACKEND_TARGET = 'http://localhost:8000'

const backendProxy = {
  target: BACKEND_TARGET,
  changeOrigin: true,
}

/**
 * Same-origin API proxy for `npm run dev`. Keep `/authorize` local because it
 * is also a SPA route; only the consent API subpaths are proxied.
 */
export const devServerProxy = {
  '^/auth(?:/|$)': backendProxy,
  '/roadmaps': backendProxy,
  '/me': backendProxy,
  '/users': backendProxy,
  '/.well-known': backendProxy,
  '/jwks': backendProxy,
  '/register': backendProxy,
  '/authorize/context': backendProxy,
  '/authorize/decision': backendProxy,
  '/token': backendProxy,
  '/revoke': backendProxy,
  '/skill': backendProxy,
} satisfies NonNullable<NonNullable<UserConfig['server']>['proxy']>
