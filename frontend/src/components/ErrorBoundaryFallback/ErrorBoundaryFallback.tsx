import { Button } from '@/components/ui/button'

export function ErrorBoundaryFallback() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
      <section className="flex max-w-md flex-col gap-4 text-center" role="alert">
        <h1 className="font-display text-3xl text-foreground">Something went wrong</h1>
        <p className="text-muted-foreground">Reload the page and try again.</p>
        <Button onClick={() => window.location.reload()} className="self-center">
          Try again
        </Button>
      </section>
    </main>
  )
}
