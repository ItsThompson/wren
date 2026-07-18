import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

import { devServerProxy } from './vite.dev-proxy.ts'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: devServerProxy,
    // Allow the dev server to read the repo-root shared/theme/*.css imported by
    // main.tsx (one level above this package). Dev-only: the production build
    // (rollup) is not fs-restricted.
    fs: {
      allow: [fileURLToPath(new URL('..', import.meta.url))],
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // The shared shared/theme/fonts.css lives at the repo root (no repo-root
      // node_modules), so its bare `@fontsource-variable/...` woff2 url()
      // specifiers cannot resolve relative to the CSS file. Pin them to this
      // package's own installed copy so Vite bundles + hashes the woff2. The
      // docs-site applies the same alias against its own node_modules; the
      // shared fonts.css stays a single physical file.
      '@fontsource-variable': fileURLToPath(
        new URL('./node_modules/@fontsource-variable', import.meta.url),
      ),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      // Vitest v4 measures every file matched by `include` by default (no `all`
      // flag needed; the v3 `coverage.all` option was removed), so the 70% floor
      // accounts for untested modules and cannot be gamed by omitting a file's
      // tests. Excludes below carve out non-source
      // (types, entry, vendored primitives, dev-only mocks).
      reporter: ['text-summary', 'text'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.d.ts',
        'src/test/**',
        'src/main.tsx',
        'src/**/index.ts',
        'src/components/ui/**', // vendored shadcn primitives
        'src/mocks/**', // dev-only MSW harness
      ],
      // Frontend floor from the testing strategy, enforced both
      // locally (`npm run test:coverage`) and in CI (`test-frontend` job).
      // vitest exits non-zero below the floor, failing the build.
      thresholds: {
        lines: 70,
      },
    },
  },
})
