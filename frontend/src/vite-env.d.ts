/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set by `npm run dev:mock`; enables the MSW zero-backend harness. */
  readonly VITE_MOCK_API?: string
  /**
   * Base URL of the backend external API (e.g. `https://api.usewren.com`).
   * Empty/undefined means same-origin relative requests (dev proxy + MSW).
   */
  readonly VITE_API_BASE_URL?: string
  /**
   * Base URL of Wren's MCP server (e.g. `https://mcp.usewren.com`). Baked at
   * build time from `MCP_PUBLIC_URL`; the onboarding wizard displays the MCP
   * endpoint derived from it. Undefined falls back to the pinned public URL.
   */
  readonly VITE_MCP_BASE_URL?: string
  /** Public Sentry DSN. An empty value disables browser error reporting. */
  readonly VITE_SENTRY_DSN?: string
  /** Release identifier attached to Sentry events. */
  readonly VITE_SENTRY_RELEASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
