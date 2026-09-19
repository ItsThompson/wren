import { execFile as execFileCallback } from 'node:child_process'
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { describe, expect, it } from 'vitest'

import {
  SensitiveValueFoundError,
  SensitiveValueRegistry,
  createSensitiveValueRegistry,
  sanitizeArtifact,
  sanitizeArtifacts,
  registerSensitiveValues,
  sanitizeArtifactFiles,
  scanArtifactBytes,
} from './artifact-sanitizer.ts'
import { SensitiveValueCategory } from './types.ts'

const execFile = promisify(execFileCallback)

function jsonBytes(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value))
}

describe('SensitiveValueRegistry', () => {
  it('redacts exact values and never includes them in absence errors', () => {
    const registry = createSensitiveValueRegistry()
    registry.register(SensitiveValueCategory.EMAIL, 'alice@example.com')
    registry.register(SensitiveValueCategory.PASSWORD, 'correct horse battery staple')

    const result = registry.redact('alice@example.com / correct horse battery staple')

    expect(result.sanitizedText).toBe('[REDACTED:email] / [REDACTED:password]')
    expect(result.redactionCounts[SensitiveValueCategory.EMAIL]).toBe(1)
    expect(() => registry.assertAbsent('alice@example.com')).toThrow(SensitiveValueFoundError)
    try {
      registry.assertAbsent('alice@example.com')
    } catch (error) {
      expect(String(error)).not.toContain('alice@example.com')
    }
  })
})

describe('artifact sanitization', () => {
  it('removes sensitive structured fields and redacts registered values', async () => {
    const registry = new SensitiveValueRegistry()
    registry.register(SensitiveValueCategory.BEARER_TOKEN, 'bearer-secret')
    registry.register(SensitiveValueCategory.USERNAME, 'alice')
    const input = jsonBytes({
      tags: { operation: 'dashboard' },
      request: { headers: { authorization: 'bearer-secret' }, query: 'token=x', body: 'alice' },
      browserStorage: { accessToken: 'bearer-secret' },
      message: 'user alice failed',
      safe: 'kept',
    })

    const result = await sanitizeArtifact({ path: 'report.json', kind: 'report', bytes: input }, registry)
    const output = new TextDecoder().decode(result.bytes)

    expect(output).toContain('"safe":"kept"')
    expect(output).toContain('[REDACTED:username]')
    expect(output).not.toContain('authorization')
    expect(output).not.toContain('browserStorage')
    expect(output).not.toContain('bearer-secret')
    expect(result.redactionCounts[SensitiveValueCategory.USERNAME]).toBe(2)
  })

  it('rebuilds trace archives and removes unsafe members', async () => {
    const work = await mkdtemp(join(tmpdir(), 'wren-artifact-test-'))
    try {
      const source = join(work, 'source')
      const archive = join(work, 'trace.zip')
      await writeFile(source, JSON.stringify({ request: { headers: { cookie: 'session' }, body: 'secret' }, method: 'GET' }))
      await execFile('zip', ['-q', archive, 'source'], { cwd: work })
      const registry = new SensitiveValueRegistry()
      registry.register(SensitiveValueCategory.SESSION_COOKIE, 'session')
      registry.register(SensitiveValueCategory.PASSWORD, 'secret')

      const result = await sanitizeArtifact({ path: archive, kind: 'trace', bytes: await readFile(archive) }, registry)
      const safeArchive = join(work, 'safe.zip')
      await writeFile(safeArchive, result.bytes)
      const extracted = join(work, 'extracted')
      await execFile('unzip', ['-qq', safeArchive, '-d', extracted])
      const rebuiltMember = await readFile(join(extracted, 'source'))
      const rebuiltText = new TextDecoder().decode(rebuiltMember)
      expect(rebuiltText).toContain('"method":"GET"')
      expect(rebuiltText).not.toContain('headers')
      expect(rebuiltText).not.toContain('session')
      expect(rebuiltText).not.toContain('secret')
    } finally {
      await rm(work, { recursive: true, force: true })
    }
  })

  it('projects attachments and recorder exports onto safe fields', async () => {
    const registry = new SensitiveValueRegistry()
    const bytes = jsonBytes({ records: [{ sequence: 1, operation: 'dashboard', status: 500, password: 'bad', callbackUrl: 'https://app.wren.test/callback?code=bad' }] })

    const result = await sanitizeArtifact({ path: 'recorder.json', kind: 'recorder', bytes }, registry)
    expect(JSON.parse(new TextDecoder().decode(result.bytes))).toEqual([{ sequence: 1, operation: 'dashboard', status: 500 }])
  })

  it('removes URL queries, fragments, and callback data from reports', async () => {
    const registry = new SensitiveValueRegistry()
    const result = await sanitizeArtifact({
      path: 'report.json',
      kind: 'report',
      bytes: jsonBytes({ url: 'https://app.wren.test/roadmaps?filter=secret#node', redirectUri: 'https://api.wren.test/callback?code=secret' }),
    }, registry)
    const report = new TextDecoder().decode(result.bytes)

    expect(report).toContain('https://app.wren.test/roadmaps')
    expect(report).not.toContain('filter=secret')
    expect(report).not.toContain('redirectUri')
    expect(report).not.toContain('callback?')
  })

  it('retains safe HTML and binary assets from a standard report', async () => {
    const registry = new SensitiveValueRegistry()
    const html = await sanitizeArtifact({
      path: 'report/index.html',
      kind: 'report-static',
      bytes: new TextEncoder().encode('<a href="https://app.wren.test/test?case=one">test</a>'),
    }, registry)
    const binary = await sanitizeArtifact({
      path: 'report/assets/font.woff2',
      kind: 'report-static',
      bytes: new Uint8Array([0, 1, 2, 3, 255]),
    }, registry)

    expect(new TextDecoder().decode(html.bytes)).toContain('https://app.wren.test/test')
    expect(new TextDecoder().decode(html.bytes)).not.toContain('?case=one')
    expect([...binary.bytes]).toEqual([0, 1, 2, 3, 255])
  })

  it('withholds allowlisted projections with invalid scalar values', async () => {
    const registry = new SensitiveValueRegistry()
    const result = await sanitizeArtifacts([
      { path: 'invalid.json', kind: 'attachment', bytes: jsonBytes({ runId: { secret: 'value' } }) },
    ], registry)

    expect(result.passed).toBe(false)
    expect(result.withheldPaths).toEqual(['invalid.json'])
  })

  it('runs a final byte scan and withholds unsafe artifacts', async () => {
    const registry = new SensitiveValueRegistry()
    registry.register(SensitiveValueCategory.CONTROL_TOKEN, 'control-secret')
    expect(scanArtifactBytes(new TextEncoder().encode('control-secret'), registry)).toContain(SensitiveValueCategory.CONTROL_TOKEN)

    const result = await sanitizeArtifacts([
      { path: 'unsafe.png', kind: 'screenshot', bytes: new TextEncoder().encode('control-secret') },
      { path: 'safe.json', kind: 'attachment', bytes: jsonBytes({ runId: 'run-1' }) },
    ], registry)
    expect(result.passed).toBe(false)
    expect(result.withheldPaths).toEqual(['unsafe.png'])
    expect(result.approvedPaths).toEqual(['safe.json'])
  })

  it('rejects malformed sensitive-value snapshots', () => {
    const registry = createSensitiveValueRegistry()
    expect(() => registerSensitiveValues(registry, { username: ['valid'], unexpected: ['secret'] })).toThrow()
    expect(() => registerSensitiveValues(registry, { username: [''] })).toThrow()
    expect(() => registerSensitiveValues(registry, { username: ['valid'] })).not.toThrow()
  })

  it('removes stale output when a scan withholds an input', async () => {
    const work = await mkdtemp(join(tmpdir(), 'wren-artifact-output-test-'))
    try {
      const input = join(work, 'invalid.json')
      const output = join(work, 'safe')
      await writeFile(input, JSON.stringify({ runId: { secret: 'value' } }))
      await mkdir(output)
      await writeFile(join(output, 'stale.log'), 'unsafe stale output')

      const result = await sanitizeArtifactFiles([{ path: input, kind: 'attachment' }], output, createSensitiveValueRegistry())

      expect(result.passed).toBe(false)
      await expect(access(output)).rejects.toThrow()
    } finally {
      await rm(work, { recursive: true, force: true })
    }
  })
})
