import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { dirname, join, relative } from 'node:path'

import { SensitiveValueCategory } from './types.ts'
import {
  classifyArtifactKind,
  createSensitiveValueRegistry,
  sanitizeArtifacts,
} from './sanitizer-core.ts'
import type { ArtifactInput, DiagnosticArtifactKind } from './types.ts'

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

async function runSanitizerCli(): Promise<void> {
  const inputDir = process.env.ARTIFACT_INPUT_DIR
  const outputDir = process.env.ARTIFACT_OUTPUT_DIR
  if (!inputDir || !outputDir) throw new Error('artifact input and output directories are required')
  const registry = createSensitiveValueRegistry()
  const valuesPath = process.env.SENSITIVE_VALUES_FILE
  if (valuesPath) {
    const values = JSON.parse(await readFile(valuesPath, 'utf8')) as Record<string, string[]>
    const categoryAliases: Record<string, SensitiveValueCategory> = {
      token: SensitiveValueCategory.BEARER_TOKEN,
      'authorization-code': SensitiveValueCategory.OAUTH_CODE,
      'code-verifier': SensitiveValueCategory.PKCE_VERIFIER,
      'client-secret': SensitiveValueCategory.INTERNAL_API_TOKEN,
    }
    for (const [category, entries] of Object.entries(values)) {
      const resolvedCategory = Object.values(SensitiveValueCategory).includes(category as SensitiveValueCategory)
        ? category as SensitiveValueCategory
        : categoryAliases[category]
      if (resolvedCategory === undefined || !Array.isArray(entries)) continue
      for (const value of entries) if (typeof value === 'string') registry.register(resolvedCategory, value)
    }
  }
  const inputs: ArtifactInput[] = await Promise.all((await walkFiles(inputDir)).map(async (path) => {
    const kindName = relative(inputDir, path).split('/')[0] ?? 'log'
    const containerKind: DiagnosticArtifactKind = ['report', 'trace', 'screenshot', 'attachment', 'log', 'recorder'].includes(kindName) ? kindName as DiagnosticArtifactKind : 'log'
    return { path, kind: classifyArtifactKind(path, containerKind), bytes: await readFile(path) }
  }))
  const result = await sanitizeArtifacts(inputs, registry)
  await rm(outputDir, { recursive: true, force: true })
  for (const artifact of result.approved) {
    const target = join(outputDir, relative(inputDir, artifact.path))
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, artifact.bytes)
  }
  if (!result.passed) {
    process.stdout.write(JSON.stringify({ passed: false, approvedPaths: result.approvedPaths, withheldPaths: result.withheldPaths, unsafeCategories: result.unsafeCategories }) + '\n')
    process.exitCode = 1
    return
  }
  process.stdout.write(JSON.stringify({ passed: true, approvedPaths: result.approvedPaths, redactionCounts: result.redactionCounts }) + '\n')
}

if (process.argv[1]?.endsWith('/artifact-sanitizer.ts')) {
  runSanitizerCli().catch(() => {
    process.stdout.write(JSON.stringify({ passed: false, error: 'artifact_sanitizer_failed' }) + '\n')
    process.exitCode = 1
  })
}
