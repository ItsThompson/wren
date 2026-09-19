export type SensitiveValueCategory = 'token' | 'authorization-code' | 'code-verifier' | 'client-secret'

export interface SensitiveValueRegistry {
  register(category: SensitiveValueCategory, value: string): void
  clear(): void
  values(): readonly string[]
}

export class InMemorySensitiveValueRegistry implements SensitiveValueRegistry {
  private readonly entries = new Map<SensitiveValueCategory, Set<string>>()

  register(category: SensitiveValueCategory, value: string): void {
    if (value.length === 0) return
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
}
