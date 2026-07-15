/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set by `npm run dev:mock`; enables the MSW zero-backend harness. */
  readonly VITE_MOCK_API?: string
  /**
   * Base URL of the backend external API (e.g. `https://api.usewren.com`).
   * Empty/undefined means same-origin relative requests (dev proxy + MSW).
   */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
