/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set by `npm run dev:mock`; enables the MSW zero-backend harness. */
  readonly VITE_MOCK_API?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
