export type Cleanup = () => void | Promise<void>

/** Owns cleanup callbacks and always runs them in reverse registration order. */
export class ResourceOwner {
  private readonly cleanups: Cleanup[] = []
  private closed = false

  add(cleanup: Cleanup): void {
    if (this.closed) throw new Error('cannot add a cleanup after the owner is closed')
    this.cleanups.push(cleanup)
  }

  async close(): Promise<void> {
    if (this.closed) return
    this.closed = true

    const failures: unknown[] = []
    while (this.cleanups.length > 0) {
      const cleanup = this.cleanups.pop()
      if (cleanup === undefined) continue
      try {
        await cleanup()
      } catch (error: unknown) {
        failures.push(error)
      }
    }

    if (failures.length === 0) return
    if (failures.length === 1) throw failures[0]
    throw new AggregateError(failures, 'one or more resources failed to close')
  }
}
