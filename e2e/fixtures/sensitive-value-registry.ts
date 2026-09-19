import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'

export type SensitiveValueCategory =
  | 'token'
  | 'authorization-code'
  | 'code-verifier'
  | 'client-secret'
  | 'session-cookie'
  | 'authorization-header'
  | 'bearer-token'
  | 'password'
  | 'refresh-token'
  | 'pkce-verifier'
  | 'control-token'
  | 'internal-api-token'
  | 'session-secret'
  | 'postgres-password'
  | 'oauth-private-key'
  | 'tls-private-key'
  | 'email'
  | 'username'

export interface SensitiveValueRegistry {
  register(category: SensitiveValueCategory, value: string): void
  clear(): void
  values(): readonly string[]
  snapshot(): Readonly<Record<SensitiveValueCategory, readonly string[]>>
}

export class InMemorySensitiveValueRegistry implements SensitiveValueRegistry {
  private readonly entries = new Map<SensitiveValueCategory, Set<string>>()

  constructor(private readonly snapshotSink?: Pick<SensitiveValueRegistry, 'register'>) {}

  register(category: SensitiveValueCategory, value: string): void {
    if (value.length === 0) return
    this.snapshotSink?.register(category, value)
    const categoryValues = this.entries.get(category) ?? new Set<string>()
    categoryValues.add(value)
    this.entries.set(category, categoryValues)
  }

  clear(): void {
    for (const values of this.entries.values()) values.clear()
    this.entries.clear()
  }

  values(): readonly string[] {
    return [...this.entries.values()].flatMap((values) => [...values])
  }

  snapshot(): Readonly<Record<SensitiveValueCategory, readonly string[]>> {
    return Object.fromEntries([...this.entries].map(([category, values]) => [category, [...values]])) as unknown as Record<SensitiveValueCategory, readonly string[]>
  }
}

const SENSITIVE_VALUE_CATEGORIES = new Set<SensitiveValueCategory>([
  'token', 'authorization-code', 'code-verifier', 'client-secret', 'session-cookie',
  'authorization-header', 'bearer-token', 'password', 'refresh-token', 'pkce-verifier',
  'control-token', 'internal-api-token', 'session-secret', 'postgres-password',
  'oauth-private-key', 'tls-private-key', 'email', 'username',
])

function parseSensitiveValueSnapshot(serialized: string): Record<string, string[]> {
  const parsed: unknown = JSON.parse(serialized)
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('sensitive-value snapshot must be an object')
  const snapshot: Record<string, string[]> = {}
  for (const [category, values] of Object.entries(parsed)) {
    if (!SENSITIVE_VALUE_CATEGORIES.has(category as SensitiveValueCategory) || !Array.isArray(values) || values.some((value) => typeof value !== 'string' || value.length === 0)) {
      throw new Error('sensitive-value snapshot contains an invalid category or value')
    }
    snapshot[category] = [...values]
  }
  return snapshot
}

export async function persistSensitiveValueSnapshot(registry: SensitiveValueRegistry, path: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  let existing: Record<string, string[]> = {}
  try {
    existing = parseSensitiveValueSnapshot(await readFile(path, 'utf8'))
  } catch (error: unknown) {
    if (!(error instanceof Error && 'code' in error && error.code === 'ENOENT')) throw error
  }
  for (const [category, values] of Object.entries(registry.snapshot())) {
    const merged = new Set([...(existing[category] ?? []), ...values])
    existing[category] = [...merged]
  }
  const temporary = `${path}.tmp-${process.pid}`
  await writeFile(temporary, JSON.stringify(existing))
  await rename(temporary, path)
}

export function sensitiveValueSnapshotPath(workerIndex: number): string | null {
  const directory = process.env.E2E_SENSITIVE_VALUES_DIR
  if (!directory) return null
  return join(directory, `worker-${workerIndex}-${process.pid}.json`)
}
