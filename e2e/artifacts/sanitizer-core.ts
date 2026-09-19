import { execFile as execFileCallback } from 'node:child_process'
import { lstat, mkdir, mkdtemp, readFile, readdir, rm, writeFile, rename } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, dirname, extname, join, normalize, relative, resolve, sep } from 'node:path'
import { promisify } from 'node:util'

import {
  SensitiveValueCategory,
  type ArtifactFileManifestEntry,
  type ArtifactInput,
  type ArtifactSafetyResult,
  type DiagnosticArtifactKind,
  type SanitizedArtifact,
} from './types.ts'

const execFile = promisify(execFileCallback)
const SAFE_ATTACHMENT_FIELDS = new Set([
  'runId', 'testId', 'attemptId', 'worker', 'retry', 'sequence', 'receivedAtIso',
  'operation', 'failureKind', 'environment', 'service', 'method', 'status',
])
const SENSITIVE_FIELD = /(authorization|headers?|cookie|cookies|query|string|querystring|body|requestbody|callbackurl|callbackuri|storage|localstorage|sessionstorage|user|breadcrumbs?|extra|extras|envelope|payload|password|token|secret|privatekey|oauth|pkce|refresh)/i
const SENSITIVE_TEXT = /(bearer\s+[^\s"']+|-----begin [^-]+private key-----|https?:\/\/[^\s"'<>?]+\?[^\s"'<>]+|[?&][A-Za-z0-9_-]+=[^\s&"'<>]+)/i
const CALLBACK_FIELD = /(callback|redirect|authorization.*url|consent)/i
const CALLBACK_URL = /https?:\/\/[^\s"'<>]*(?:callback|redirect|authorize|consent)[^\s"'<>]*/i
const STATIC_REPORT_EXTENSIONS = new Set(['.html', '.htm', '.css', '.js', '.mjs', '.svg', '.ico', '.woff', '.woff2', '.map'])
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp'])
const CATEGORY_BY_FIELD: readonly [RegExp, SensitiveValueCategory][] = [
  [/authorization|bearer/i, SensitiveValueCategory.AUTHORIZATION_HEADER],
  [/cookie/i, SensitiveValueCategory.SESSION_COOKIE],
  [/password/i, SensitiveValueCategory.PASSWORD],
  [/oauth|callback|pkce|code/i, SensitiveValueCategory.OAUTH_CODE],
  [/refresh/i, SensitiveValueCategory.REFRESH_TOKEN],
  [/private.?key|tls/i, SensitiveValueCategory.TLS_PRIVATE_KEY],
  [/token|secret/i, SensitiveValueCategory.CONTROL_TOKEN],
  [/email/i, SensitiveValueCategory.EMAIL],
  [/username|user/i, SensitiveValueCategory.USERNAME],
]

function emptyCounts(): Record<SensitiveValueCategory, number> {
  return Object.fromEntries(Object.values(SensitiveValueCategory).map((category) => [category, 0])) as Record<SensitiveValueCategory, number>
}

function mergeCounts(target: Record<SensitiveValueCategory, number>, source: Readonly<Record<SensitiveValueCategory, number>>): void {
  for (const category of Object.values(SensitiveValueCategory)) target[category] += source[category] ?? 0
}

function categoryForField(field: string): SensitiveValueCategory {
  return CATEGORY_BY_FIELD.find(([pattern]) => pattern.test(field))?.[1] ?? SensitiveValueCategory.INTERNAL_API_TOKEN
}

export class SensitiveValueFoundError extends Error {
  readonly category: SensitiveValueCategory
  constructor(category: SensitiveValueCategory) {
    super(`sensitive value found (${category})`)
    this.name = 'SensitiveValueFoundError'
    this.category = category
  }
}

export class UnsafeArtifactError extends Error {
  readonly categories: readonly SensitiveValueCategory[]
  constructor(categories: readonly SensitiveValueCategory[] = []) {
    super('artifact safety could not be proven')
    this.name = 'UnsafeArtifactError'
    this.categories = categories
  }
}

export class SensitiveValueRegistry {
  private readonly values = new Map<SensitiveValueCategory, Set<string>>()

  register(category: SensitiveValueCategory, value: string): void {
    if (value.length === 0) return
    const categoryValues = this.values.get(category) ?? new Set<string>()
    categoryValues.add(value)
    this.values.set(category, categoryValues)
  }

  redact(serializedText: string) {
    const redactionCounts = emptyCounts()
    let sanitizedText = serializedText
    for (const category of Object.values(SensitiveValueCategory)) {
      const values = [...(this.values.get(category) ?? [])].sort((left, right) => right.length - left.length)
      for (const value of values) {
        const occurrences = sanitizedText.split(value).length - 1
        if (occurrences > 0) {
          redactionCounts[category] += occurrences
          sanitizedText = sanitizedText.split(value).join(`[REDACTED:${category}]`)
        }
      }
    }
    return { sanitizedText, redactionCounts }
  }

  assertAbsent(serializedText: string): void {
    for (const category of Object.values(SensitiveValueCategory)) {
      if ([...(this.values.get(category) ?? [])].some((value) => serializedText.includes(value))) throw new SensitiveValueFoundError(category)
    }
  }

  categoriesFound(serializedBytes: Uint8Array): SensitiveValueCategory[] {
    const bytes = Buffer.from(serializedBytes)
    return [...this.values].flatMap(([category, values]) => [...values].some((value) => bytes.includes(Buffer.from(value))) ? [category] : [])
  }
}

function sanitizeUrl(value: string): string {
  try {
    const parsed = new URL(value)
    if (CALLBACK_FIELD.test(parsed.pathname)) return '[REDACTED:callback-url]'
    return `${parsed.origin}${parsed.pathname}`
  } catch {
    return value.replace(/[?].*$/, '').replace(/#.*/, '')
  }
}

function sanitizeString(value: string, registry: SensitiveValueRegistry): string {
  const redacted = registry.redact(value).sanitizedText
  return redacted.replace(/https?:\/\/[^\s"'<>]+/gi, sanitizeUrl)
}

function sanitizeStructuredValue(value: unknown, registry: SensitiveValueRegistry): unknown {
  if (Array.isArray(value)) return value.map((item) => sanitizeStructuredValue(item, registry))
  if (typeof value === 'string') return sanitizeString(value, registry)
  if (value === null || typeof value !== 'object') return value
  const sanitized: Record<string, unknown> = {}
  for (const [childField, fieldValue] of Object.entries(value)) {
    const normalizedField = childField.replace(/[^a-z]/gi, '')
    if (SENSITIVE_FIELD.test(normalizedField) || CALLBACK_FIELD.test(normalizedField)) continue
    sanitized[childField] = sanitizeStructuredValue(fieldValue, registry)
  }
  return sanitized
}

function parseStructuredText(text: string, kind: DiagnosticArtifactKind, registry: SensitiveValueRegistry) {
  const counts = emptyCounts()
  const inputRedaction = registry.redact(text)
  mergeCounts(counts, inputRedaction.redactionCounts)
  try {
    const parsed = JSON.parse(inputRedaction.sanitizedText.trim()) as unknown
    const redacted = registry.redact(JSON.stringify(sanitizeStructuredValue(parsed, registry)))
    mergeCounts(counts, redacted.redactionCounts)
    return { text: `${redacted.sanitizedText}\n`, counts }
  } catch {
    if (kind === 'report-static') {
      const sanitizedText = sanitizeString(text, registry)
      return { text: sanitizedText, counts }
    }
    if (kind === 'trace' || kind === 'report') {
      const lines = inputRedaction.sanitizedText.trim().split('\n').filter((line) => line.length > 0)
      try {
        const safeLines = lines.map((line) => JSON.stringify(sanitizeStructuredValue(JSON.parse(line) as unknown, registry)))
        const redacted = registry.redact(safeLines.join('\n'))
        mergeCounts(counts, redacted.redactionCounts)
        return { text: `${redacted.sanitizedText}\n`, counts }
      } catch {
        throw new UnsafeArtifactError([SensitiveValueCategory.INTERNAL_API_TOKEN])
      }
    }
    if (kind !== 'log') throw new UnsafeArtifactError([SensitiveValueCategory.INTERNAL_API_TOKEN])
    const redacted = registry.redact(text)
    mergeCounts(counts, redacted.redactionCounts)
    const safeLines = redacted.sanitizedText
      .split('\n')
      .filter((line) => !SENSITIVE_FIELD.test(line.replace(/[^a-z]/gi, '')) && !SENSITIVE_TEXT.test(line))
      .map((line) => sanitizeString(line, registry))
    return { text: safeLines.join('\n'), counts }
  }
}

function finalScan(bytes: Uint8Array, registry: SensitiveValueRegistry): SensitiveValueCategory[] {
  const categories = registry.categoriesFound(bytes)
  let text: string
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes) } catch { return categories }
  if (SENSITIVE_TEXT.test(text) || CALLBACK_URL.test(text)) categories.push(SensitiveValueCategory.INTERNAL_API_TOKEN)
  for (const match of text.matchAll(/["']([^"']+)["']\s*:/g)) {
    const field = match[1] ?? ''
    if (SENSITIVE_FIELD.test(field.replace(/[^a-z]/gi, '')) || CALLBACK_FIELD.test(field)) categories.push(categoryForField(field))
  }
  for (const match of text.matchAll(/(?:^|[,{;\s])([A-Za-z_$][\w$-]*)\s*(?::|=)/g)) {
    const field = match[1] ?? ''
    if (SENSITIVE_FIELD.test(field.replace(/[^a-z]/gi, '')) || CALLBACK_FIELD.test(field)) categories.push(categoryForField(field))
  }
  return [...new Set(categories)]
}

async function walkArchiveFiles(root: string): Promise<string[]> {
  const files: string[] = []
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = join(root, entry.name)
    const metadata = await lstat(path)
    if (metadata.isSymbolicLink()) throw new UnsafeArtifactError()
    if (metadata.isDirectory()) files.push(...await walkArchiveFiles(path))
    else if (metadata.isFile()) files.push(path)
    else throw new UnsafeArtifactError()
  }
  return files
}

export function classifyArtifactKind(path: string, parentKind: DiagnosticArtifactKind = 'report'): DiagnosticArtifactKind {
  const extension = extname(path).toLowerCase()
  if (IMAGE_EXTENSIONS.has(extension)) return 'screenshot'
  if (extension === '.zip') return parentKind
  if (parentKind === 'report' && STATIC_REPORT_EXTENSIONS.has(extension)) return 'report-static'
  return parentKind
}

function validateArchiveListing(listing: string, registry: SensitiveValueRegistry): void {
  const memberNames = listing.split('\n').filter((name) => name.length > 0)
  for (const memberName of memberNames) {
    const normalized = memberName.replaceAll('\\', '/')
    const hasWindowsRoot = normalized.length > 2 && /^[A-Za-z]:$/.test(normalized.slice(0, 2)) && normalized[2] === '/'
    if (normalized.includes('\0') || normalized.startsWith('/') || hasWindowsRoot || normalize(normalized).split('/').includes('..')) throw new UnsafeArtifactError()
    const categories = archiveMetadataCategories(memberName, registry)
    if (categories.length > 0) throw new UnsafeArtifactError(categories)
  }
}

function archiveMetadataCategories(text: string, registry: SensitiveValueRegistry): SensitiveValueCategory[] {
  const bytes = new TextEncoder().encode(text)
  const categories = registry.categoriesFound(bytes)
  if (SENSITIVE_TEXT.test(text) || CALLBACK_URL.test(text)) categories.push(SensitiveValueCategory.INTERNAL_API_TOKEN)
  return [...new Set(categories)]
}

function validateArchiveMetadata(verboseListing: string, registry: SensitiveValueRegistry): void {
  const attributes = verboseListing.matchAll(/Unix file attributes \(\d+ octal\):\s+([^\r\n]+)/g)
  for (const match of attributes) {
    const fileType = match[1]?.trim()[0]
    if (fileType !== '-' && fileType !== 'd') throw new UnsafeArtifactError()
  }
  const categories = archiveMetadataCategories(verboseListing, registry)
  if (categories.length > 0) throw new UnsafeArtifactError(categories)
}

async function rebuildZip(bytes: Uint8Array, registry: SensitiveValueRegistry, archiveKind: DiagnosticArtifactKind) {
  const work = await mkdtemp(join(tmpdir(), 'wren-artifact-'))
  const input = join(work, 'input.zip')
  const extracted = join(work, 'extracted')
  const output = join(work, 'safe.zip')
  const counts = emptyCounts()
  try {
    await writeFile(input, bytes)
    const listing = await execFile('unzip', ['-Z1', input], { maxBuffer: 2 * 1024 * 1024 })
    validateArchiveListing(listing.stdout, registry)
    const verboseListing = await execFile('unzip', ['-Z', '-v', input], { maxBuffer: 4 * 1024 * 1024 })
    validateArchiveMetadata(verboseListing.stdout, registry)
    await execFile('unzip', ['-qq', input, '-d', extracted])
    for (const path of await walkArchiveFiles(extracted)) {
      const member = await readFile(path)
      const kind = classifyArtifactKind(path, archiveKind)
      const safe = sanitizeBytes(member, kind, registry)
      mergeCounts(counts, safe.counts)
      await writeFile(path, safe.bytes)
    }
    await execFile('zip', ['-q', '-r', '-X', output, '.'], { cwd: extracted })
    const rebuiltBytes = await readFile(output)
    const rebuiltListing = await execFile('unzip', ['-Z1', output], { maxBuffer: 2 * 1024 * 1024 })
    validateArchiveListing(rebuiltListing.stdout, registry)
    const rebuiltMetadata = await execFile('unzip', ['-Z', '-v', output], { maxBuffer: 4 * 1024 * 1024 })
    validateArchiveMetadata(rebuiltMetadata.stdout, registry)
    const categories = finalScan(rebuiltBytes, registry)
    if (categories.length > 0) throw new UnsafeArtifactError(categories)
    return { bytes: rebuiltBytes, counts }
  } catch (error) {
    if (error instanceof UnsafeArtifactError) throw error
    throw new UnsafeArtifactError([SensitiveValueCategory.INTERNAL_API_TOKEN])
  } finally { await rm(work, { recursive: true, force: true }) }
}

function sanitizeBytes(bytes: Uint8Array, kind: DiagnosticArtifactKind, registry: SensitiveValueRegistry) {
  if (kind === 'screenshot' || kind === 'report-static') {
    let text: string
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes) } catch {
      const categories = finalScan(bytes, registry)
      if (categories.length > 0) throw new UnsafeArtifactError(categories)
      return { bytes, counts: emptyCounts() }
    }
    if (kind === 'screenshot') {
      const categories = finalScan(bytes, registry)
      if (categories.length > 0) throw new UnsafeArtifactError(categories)
      return { bytes, counts: emptyCounts() }
    }
    const parsedStatic = parseStructuredText(text, kind, registry)
    const staticBytes = new TextEncoder().encode(parsedStatic.text)
    const staticCategories = finalScan(staticBytes, registry)
    if (staticCategories.length > 0) throw new UnsafeArtifactError(staticCategories)
    return { bytes: staticBytes, counts: parsedStatic.counts }
  }
  let text: string
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes) } catch { throw new UnsafeArtifactError([SensitiveValueCategory.INTERNAL_API_TOKEN]) }
  const parsed = parseStructuredText(text, kind, registry)
  const output = new TextEncoder().encode(parsed.text)
  const categories = finalScan(output, registry)
  if (categories.length > 0) throw new UnsafeArtifactError(categories)
  return { bytes: output, counts: parsed.counts }
}

function isArchive(path: string): boolean { return extname(path).toLowerCase() === '.zip' }

function hasControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    if (value.charCodeAt(index) < 32) return true
  }
  return false
}

function validateProjectionValue(field: string, value: unknown): unknown {
  const integerFields = new Set(['worker', 'retry', 'sequence', 'status'])
  if (field === 'status' && value === null) return null
  if (integerFields.has(field)) {
    if (typeof value !== 'number' || !Number.isInteger(value) || value < 0 || value > (field === 'status' ? 599 : 1_000_000_000)) throw new UnsafeArtifactError()
    return value
  }
  if (field === 'failureKind') {
    if (value !== 'upstream' && value !== 'network') throw new UnsafeArtifactError()
    return value
  }
  const hasUnsafeCharacters = typeof value === 'string' && hasControlCharacter(value)
  if (typeof value !== 'string' || value.length === 0 || value.length > 200 || hasUnsafeCharacters || value.includes('?') || value.includes('#')) throw new UnsafeArtifactError()
  if (field === 'receivedAtIso' && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) throw new UnsafeArtifactError()
  return value
}

function attachmentProjection(value: unknown): unknown {
  const records = Array.isArray(value) ? value : typeof value === 'object' && value !== null && Array.isArray((value as { records?: unknown }).records) ? (value as { records: unknown[] }).records : [value]
  return records.map((record) => {
    if (typeof record !== 'object' || record === null || Array.isArray(record)) throw new UnsafeArtifactError()
    const projection: Record<string, unknown> = {}
    for (const [field, fieldValue] of Object.entries(record)) {
      if (SAFE_ATTACHMENT_FIELDS.has(field)) projection[field] = validateProjectionValue(field, fieldValue)
    }
    if (Object.keys(projection).length === 0) throw new UnsafeArtifactError()
    return projection
  })
}

export async function sanitizeArtifact(input: ArtifactInput, registry: SensitiveValueRegistry): Promise<SanitizedArtifact> {
  const effectiveKind = classifyArtifactKind(input.path, input.kind)
  let safe
  if (isArchive(input.path)) safe = await rebuildZip(input.bytes, registry, effectiveKind)
  else if (effectiveKind === 'attachment' || effectiveKind === 'recorder') {
    let value: unknown
    try { value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(input.bytes)) } catch { throw new UnsafeArtifactError() }
    safe = sanitizeBytes(new TextEncoder().encode(JSON.stringify(attachmentProjection(value))), 'recorder', registry)
  } else safe = sanitizeBytes(input.bytes, effectiveKind, registry)
  return { path: input.path, kind: effectiveKind, bytes: safe.bytes, redactionCounts: safe.counts }
}

export async function sanitizeArtifacts(inputs: readonly ArtifactInput[], registry: SensitiveValueRegistry): Promise<ArtifactSafetyResult> {
  const approved: SanitizedArtifact[] = []
  const withheldPaths: string[] = []
  const redactionCounts = emptyCounts()
  const unsafeCategories = new Set<SensitiveValueCategory>()
  for (const input of inputs) {
    try {
      const artifact = await sanitizeArtifact(input, registry)
      approved.push(artifact)
      mergeCounts(redactionCounts, artifact.redactionCounts)
    } catch (error) {
      withheldPaths.push(input.path)
      if (error instanceof UnsafeArtifactError) for (const category of error.categories) unsafeCategories.add(category)
    }
  }
  return { approved, approvedPaths: approved.map((artifact) => artifact.path), withheldPaths, redactionCounts, unsafeCategories: [...unsafeCategories], passed: withheldPaths.length === 0 }
}

export async function sanitizeArtifactFiles(inputs: readonly ArtifactFileManifestEntry[], outputDir: string, registry: SensitiveValueRegistry): Promise<ArtifactSafetyResult> {
  const resolvedOutputDir = resolve(outputDir)
  const overlapsOutput = inputs.some((input) => {
    const resolvedInput = resolve(input.path)
    return resolvedInput === resolvedOutputDir || resolvedInput.startsWith(`${resolvedOutputDir}${sep}`)
  })
  if (overlapsOutput) throw new Error('artifact input cannot overlap output directory')
  const artifacts = await Promise.all(inputs.map(async (input) => ({ ...input, bytes: await readFile(input.path) })))
  const result = await sanitizeArtifacts(artifacts, registry)
  await rm(outputDir, { recursive: true, force: true })
  if (!result.passed) return result

  const outputParent = dirname(outputDir)
  await mkdir(outputParent, { recursive: true })
  const stagingDir = await mkdtemp(join(outputParent, `.${basename(outputDir)}-`))
  try {
    for (const artifact of result.approved) {
      const target = resolve(stagingDir, relative(resolve('/'), resolve(artifact.path)))
      await mkdir(dirname(target), { recursive: true })
      await writeFile(target, artifact.bytes)
    }
    await rename(stagingDir, outputDir)
  } catch (error) {
    await rm(stagingDir, { recursive: true, force: true })
    await rm(outputDir, { recursive: true, force: true })
    throw error
  }
  return result
}

export function scanArtifactBytes(bytes: Uint8Array, registry: SensitiveValueRegistry): readonly SensitiveValueCategory[] { return finalScan(bytes, registry) }
export function createSensitiveValueRegistry(): SensitiveValueRegistry { return new SensitiveValueRegistry() }
