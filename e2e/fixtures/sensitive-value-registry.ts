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

export type SensitiveValueSnapshot = Readonly<Partial<Record<SensitiveValueCategory, readonly string[]>>>

export interface SensitiveValueRegistry {
  register(category: SensitiveValueCategory, value: string): void
  clear(): void
  values(): readonly string[]
  snapshot(): SensitiveValueSnapshot
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

  snapshot(): SensitiveValueSnapshot {
    const snapshot: Partial<Record<SensitiveValueCategory, readonly string[]>> = {}
    for (const [category, values] of this.entries) snapshot[category] = [...values]
    return snapshot
  }
}

const SENSITIVE_VALUE_CATEGORIES: readonly SensitiveValueCategory[] = [
  'token', 'authorization-code', 'code-verifier', 'client-secret', 'session-cookie',
  'authorization-header', 'bearer-token', 'password', 'refresh-token', 'pkce-verifier',
  'control-token', 'internal-api-token', 'session-secret', 'postgres-password',
  'oauth-private-key', 'tls-private-key', 'email', 'username',
]

function isSensitiveValueCategory(value: string): value is SensitiveValueCategory {
  return SENSITIVE_VALUE_CATEGORIES.some((category) => category === value)
}

function parseSensitiveValueSnapshot(serialized: string): Partial<Record<SensitiveValueCategory, string[]>> {
  const parsed: unknown = JSON.parse(serialized)
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('sensitive-value snapshot must be an object')
  const snapshot: Partial<Record<SensitiveValueCategory, string[]>> = {}
  for (const [category, values] of Object.entries(parsed)) {
    if (!isSensitiveValueCategory(category) || !Array.isArray(values) || values.some((value) => typeof value !== 'string' || value.length === 0)) {
      throw new Error('sensitive-value snapshot contains an invalid category or value')
    }
    snapshot[category] = [...values]
  }
  return snapshot
}

export async function persistSensitiveValueSnapshot(registry: SensitiveValueRegistry, path: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  let existing: Partial<Record<SensitiveValueCategory, string[]>> = {}
  try {
    existing = parseSensitiveValueSnapshot(await readFile(path, 'utf8'))
  } catch (error: unknown) {
    if (!(error instanceof Error && 'code' in error && error.code === 'ENOENT')) throw error
  }
  const snapshot = registry.snapshot()
  for (const category of SENSITIVE_VALUE_CATEGORIES) {
    const values = snapshot[category]
    if (values === undefined) continue
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
