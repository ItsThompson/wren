import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      // Measure every file matched by `include`, not just files a test imported,
      // so the 70% floor accounts for untested modules and cannot be gamed by
      // omitting a file's tests (Ticket 30 / #5 review). Excludes below carve
      // out non-source (types, entry, vendored primitives, dev-only mocks).
      all: true,
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
      // Frontend floor from the testing strategy (section 13), enforced both
      // locally (`npm run test:coverage`) and in CI (`test-frontend` job,
      // Ticket 30). vitest exits non-zero below the floor, failing the build.
      thresholds: {
        lines: 70,
      },
    },
  },
})
