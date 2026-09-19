import type { McpCallToolResult } from './types'

export type StructuredContent = Record<string, unknown>
export type ValueParser<T> = (value: unknown, field: string) => T

export function structuredContent(result: McpCallToolResult): StructuredContent {
  if (result.isError === true) throw new Error('MCP tool returned an error result')
  return record(result.structuredContent, 'structuredContent')
}

export function record(value: unknown, field: string): StructuredContent {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${field} must be an object`)
  }
  return value as StructuredContent
}

export function stringValue(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new Error(`${field} must be a string`)
  return value
}

export function numberValue(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${field} must be a finite number`)
  return value
}

export function booleanValue(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`${field} must be a boolean`)
  return value
}

export function nullableString(value: unknown, field: string): string | null {
  if (value === null) return null
  return stringValue(value, field)
}

export function value<T>(source: StructuredContent, field: string, parser: ValueParser<T>): T {
  return parser(source[field], field)
}

export function array<T>(valueToParse: unknown, field: string, parser: ValueParser<T>): T[] {
  if (!Array.isArray(valueToParse)) throw new Error(`${field} must be an array`)
  return valueToParse.map((item, index) => parser(item, `${field}[${index}]`))
}

export function stringArray(valueToParse: unknown, field: string): string[] {
  return array(valueToParse, field, stringValue)
}

export function objectMap<T>(valueToParse: unknown, field: string, parser: ValueParser<T>): Record<string, T> {
  const source = record(valueToParse, field)
  return Object.fromEntries(Object.entries(source).map(([key, item]) => [key, parser(item, `${field}.${key}`)]))
}
