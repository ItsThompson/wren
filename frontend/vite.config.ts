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
      // Frontend floor from the testing strategy (section 13). The CI gate that
      // fails the build below this lands in Ticket 30; the threshold is
      // established here so `npm run test:coverage` enforces it locally now.
      thresholds: {
        lines: 70,
      },
    },
  },
})
