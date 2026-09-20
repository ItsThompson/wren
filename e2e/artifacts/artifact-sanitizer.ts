import { mkdir, mkdtemp, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises'
import { basename, dirname, join, relative } from 'node:path'

import { SensitiveValueCategory } from './types.ts'
import {
  classifyArtifactKind,
  createSensitiveValueRegistry,
  sanitizeArtifacts,
  assertNoPathOverlap,
  type SensitiveValueRegistry,
} from './sanitizer-core.ts'
import type { ArtifactInput, DiagnosticArtifactKind } from './types.ts'

const CATEGORY_ALIASES: Readonly<Record<string, SensitiveValueCategory>> = {
  token: SensitiveValueCategory.BEARER_TOKEN,
  'authorization-code': SensitiveValueCategory.OAUTH_CODE,
  'code-verifier': SensitiveValueCategory.PKCE_VERIFIER,
  'client-secret': SensitiveValueCategory.INTERNAL_API_TOKEN,
}

export * from './sanitizer-core.ts'
export * from './types.ts'

async function walkFiles(root: string): Promise<string[]> {
  const files: string[] = []
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) files.push(...await walkFiles(path))
    else if (entry.isFile()) files.push(path)
  }
  return files
}

export function registerSensitiveValues(registry: SensitiveValueRegistry, values: unknown): void {
  if (values === null || typeof values !== 'object' || Array.isArray(values)) throw new Error('sensitive values must be an object')
  for (const [category, entries] of Object.entries(values)) {
    const resolvedCategory = Object.values(SensitiveValueCategory).includes(category as SensitiveValueCategory)
      ? category as SensitiveValueCategory
      : CATEGORY_ALIASES[category]
    if (resolvedCategory === undefined || !Array.isArray(entries) || entries.some((value) => typeof value !== 'string' || value.length === 0)) {
      throw new Error('sensitive values contain an invalid category or entry')
    }
    for (const value of entries) registry.register(resolvedCategory, value)
  }
}

async function runSanitizerCli(): Promise<void> {
  const inputDir = process.env.ARTIFACT_INPUT_DIR
  const outputDir = process.env.ARTIFACT_OUTPUT_DIR
  if (!inputDir || !outputDir) throw new Error('artifact input and output directories are required')
  assertNoPathOverlap([inputDir], outputDir)
  const registry = createSensitiveValueRegistry()
  const valuesPath = process.env.SENSITIVE_VALUES_FILE
  if (valuesPath) registerSensitiveValues(registry, JSON.parse(await readFile(valuesPath, 'utf8')))
  const inputs: ArtifactInput[] = await Promise.all((await walkFiles(inputDir)).map(async (path) => {
    const kindName = relative(inputDir, path).split('/')[0] ?? 'log'
    const containerKind: DiagnosticArtifactKind = ['report', 'trace', 'screenshot', 'attachment', 'log', 'recorder'].includes(kindName) ? kindName as DiagnosticArtifactKind : 'log'
    return { path, kind: classifyArtifactKind(path, containerKind), bytes: await readFile(path) }
  }))
  const result = await sanitizeArtifacts(inputs, registry)
  if (!result.passed) {
    await rm(outputDir, { recursive: true, force: true })
    process.stdout.write(JSON.stringify({ passed: false, approvedPaths: result.approvedPaths, withheldPaths: result.withheldPaths, unsafeCategories: result.unsafeCategories }) + '\n')
    process.exitCode = 1
    return
  }

  const outputParent = dirname(outputDir)
  await mkdir(outputParent, { recursive: true })
  const stagingDir = await mkdtemp(join(outputParent, `.${basename(outputDir)}-`))
  try {
    for (const artifact of result.approved) {
      const target = join(stagingDir, relative(inputDir, artifact.path))
      await mkdir(dirname(target), { recursive: true })
      await writeFile(target, artifact.bytes)
    }
    await rm(outputDir, { recursive: true, force: true })
    await rename(stagingDir, outputDir)
  } catch (error) {
    await rm(stagingDir, { recursive: true, force: true })
    throw error
  }
  process.stdout.write(JSON.stringify({ passed: true, approvedPaths: result.approvedPaths, redactionCounts: result.redactionCounts }) + '\n')
}

if (process.argv[1]?.endsWith('/artifact-sanitizer.ts')) {
  runSanitizerCli().catch(() => {
    process.stdout.write(JSON.stringify({ passed: false, error: 'artifact_sanitizer_failed' }) + '\n')
    process.exitCode = 1
  })
}
