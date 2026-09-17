import type { FallbackRender } from '@sentry/react'

import { Button } from '@/components/ui/button'

export const ErrorBoundaryFallback: FallbackRender = ({ resetError }) => (
  <main className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
    <section className="flex max-w-md flex-col gap-4 text-center" role="alert">
      <h1 className="font-display text-3xl text-foreground">Something went wrong</h1>
      <p className="text-muted-foreground">Reload the page and try again.</p>
      <Button onClick={resetError} className="self-center">Try again</Button>
    </section>
  </main>
)
