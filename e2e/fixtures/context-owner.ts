export interface AsyncResource {
  name: string
  close(): Promise<void>
}

export interface ContextOwner {
  own<T extends AsyncResource>(resource: T): T
  closeAll(): Promise<void>
}

export class ResourceCleanupError extends AggregateError {
  constructor(failures: readonly unknown[]) {
    super(failures, 'one or more owned resources failed to close')
    this.name = 'ResourceCleanupError'
  }
}

export class OwnedContextResources implements ContextOwner {
  private readonly resources: AsyncResource[] = []
  private closed = false

  own<T extends AsyncResource>(resource: T): T {
    if (this.closed) throw new Error('cannot own a resource after cleanup has started')
    this.resources.push(resource)
    return resource
  }

  async closeAll(): Promise<void> {
    if (this.closed) return
    this.closed = true

    const failures: unknown[] = []
    while (this.resources.length > 0) {
      const resource = this.resources.pop()
      if (resource === undefined) continue
      try {
        await resource.close()
      } catch (error: unknown) {
        failures.push(new NamedCleanupFailure(resource.name, error))
      }
    }

    if (failures.length > 0) throw new ResourceCleanupError(failures)
  }
}

export const ContextOwner = OwnedContextResources

class NamedCleanupFailure extends Error {
  constructor(resourceName: string, cause: unknown) {
    super(`failed to close owned resource "${resourceName}"`, { cause })
    this.name = 'NamedCleanupFailure'
  }
}

export function ownDisposable<T extends { dispose(): Promise<void> }>(
  owner: ContextOwner,
  resource: T,
  name: string,
): T {
  owner.own({ name, close: () => resource.dispose() })
  return resource
}

export function ownClosable<T extends { close(): Promise<void> }>(
  owner: ContextOwner,
  resource: T,
  name: string,
): T {
  owner.own({ name, close: () => resource.close() })
  return resource
}
