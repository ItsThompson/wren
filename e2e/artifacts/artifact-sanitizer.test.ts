import { execFile as execFileCallback } from 'node:child_process'
import { access, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
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

  it('withholds ZIP symlinks and unsafe member names', async () => {
    const work = await mkdtemp(join(tmpdir(), 'wren-artifact-zip-test-'))
    try {
      const target = join(work, 'target')
      const link = join(work, 'link')
      const archive = join(work, 'unsafe.zip')
      await writeFile(target, 'safe')
      await symlink('target', link)
      await execFile('zip', ['-q', '-y', archive, 'target', 'link'], { cwd: work })

      const result = await sanitizeArtifacts([{
        path: archive,
        kind: 'trace',
        bytes: await readFile(archive),
      }], createSensitiveValueRegistry())

      expect(result.passed).toBe(false)
      expect(result.withheldPaths).toEqual([archive])

      const callbackName = join(work, 'callback?code=secret')
      const callbackArchive = join(work, 'callback-name.zip')
      await writeFile(callbackName, 'safe')
      await execFile('zip', ['-q', '-j', callbackArchive, callbackName], { cwd: work })
      const callbackResult = await sanitizeArtifacts([{
        path: callbackArchive,
        kind: 'trace',
        bytes: await readFile(callbackArchive),
      }], createSensitiveValueRegistry())
      expect(callbackResult.passed).toBe(false)
      expect(callbackResult.withheldPaths).toEqual([callbackArchive])
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

  it('removes Playwright fill values while preserving unrelated report values', async () => {
    const registry = new SensitiveValueRegistry()
    registry.register(SensitiveValueCategory.PASSWORD, 'credential-value')
    const result = await sanitizeArtifact({
      path: 'trace/action.trace',
      kind: 'trace',
      bytes: jsonBytes({
        type: 'action',
        method: 'fill',
        params: { selector: '#email', value: 'credential-value' },
        details: { value: 'useful-report-value' },
        __playwright_value_0: 'credential-value',
      }),
    }, registry)
    const output = new TextDecoder().decode(result.bytes)

    expect(output).toContain('useful-report-value')
    expect(output).not.toContain('credential-value')
    expect(output).not.toContain('__playwright_value_')
    expect(() => registry.assertAbsent(output)).not.toThrow()
  })

  it('removes Playwright value fields from static report assets', async () => {
    const registry = new SensitiveValueRegistry()
    registry.register(SensitiveValueCategory.PASSWORD, 'credential-value')
    registry.register(SensitiveValueCategory.PASSWORD, 'second-credential')
    const result = await sanitizeArtifact({
      path: 'report/app.js',
      kind: 'report-static',
      bytes: new TextEncoder().encode(
        'const report = { value: "useful-report-value", __playwright_value_0: "credential-value" }; __playwright_value_1 = "second-credential";',
      ),
    }, registry)
    const output = new TextDecoder().decode(result.bytes)

    expect(output).toContain('useful-report-value')
    expect(output).not.toContain('credential-value')
    expect(output).not.toContain('second-credential')
    expect(output).not.toContain('__playwright_value_')
    expect(() => registry.assertAbsent(output)).not.toThrow()
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

  it('withholds static assets that use dynamic sensitive writes', async () => {
    const result = await sanitizeArtifacts([
      { path: 'report/object.js', kind: 'report-static', bytes: new TextEncoder().encode('const data={headers:{authorization:"unregistered-secret"}};') },
      { path: 'report/attribute.js', kind: 'report-static', bytes: new TextEncoder().encode('element.setAttribute("authorization", value);') },
      { path: 'report/bracket.js', kind: 'report-static', bytes: new TextEncoder().encode('request["body"] = value;') },
      { path: 'report/storage.js', kind: 'report-static', bytes: new TextEncoder().encode('localStorage.setItem("request", value);') },
    ], createSensitiveValueRegistry())

    expect(result.passed).toBe(false)
    expect(result.withheldPaths).toEqual([
      'report/object.js',
      'report/attribute.js',
      'report/bracket.js',
      'report/storage.js',
    ])
  })

  it('preserves optional chaining in safe static assets', async () => {
    const result = await sanitizeArtifact({
      path: 'report/app.js',
      kind: 'report-static',
      bytes: new TextEncoder().encode('const value = object?.field;'),
    }, createSensitiveValueRegistry())

    expect(new TextDecoder().decode(result.bytes)).toContain('object?.field')
  })

  it('retains plain logs while replacing request-bearing lines with a safe marker', async () => {
    const result = await sanitizeArtifacts([
      { path: 'log/backend.log', kind: 'log', bytes: new TextEncoder().encode('POST /endpoint {"foo":"bar"}') },
      { path: 'log/frontend.log', kind: 'log', bytes: new TextEncoder().encode('request body: foo=bar') },
    ], createSensitiveValueRegistry())

    expect(result.passed).toBe(true)
    expect(result.withheldPaths).toEqual([])
    expect(new TextDecoder().decode(result.approved[0]?.bytes)).toContain('[REDACTED:unsafe-log-message]')
    expect(new TextDecoder().decode(result.approved[1]?.bytes)).toContain('[REDACTED:unsafe-log-message]')
  })

  it('sanitizes Compose-prefixed logs from all six E2E services', async () => {
    const logs = [
      ['ingress', 'wren-ingress-1 | 10.0.0.4 - - [19/Sep/2026:17:00:00 +0000] "GET /roadmaps?token=secret HTTP/1.1" 200 123 "-" "Mozilla"'],
      ['frontend', 'wren-frontend-1 | frontend server ready'],
      ['backend', '{"level":"info","message":"wren backend ready"}'],
      ['mcp', 'wren-mcp-1 | {"level":"info","message":"mcp ready"}'],
      ['postgres', 'wren-postgres-1 | 2026-09-19 17:00:00.123 UTC [42] LOG: database system is ready to accept connections'],
      ['recorder', 'wren-recorder-1 | recorder ready'],
    ] as const
    const result = await sanitizeArtifacts(logs.map(([service, line]) => ({
      path: `log/${service}.log`,
      kind: 'log' as const,
      bytes: new TextEncoder().encode(line),
    })), createSensitiveValueRegistry())

    expect(result.passed).toBe(true)
    expect(result.approvedPaths).toHaveLength(6)
    expect(result.withheldPaths).toEqual([])
    const output = result.approved.map((artifact) => new TextDecoder().decode(artifact.bytes)).join('\n')
    expect(output).toContain('"path":"/roadmaps"')
    expect(output).not.toContain('token=secret')
    expect(output).toContain('"format":"postgres-log"')
  })

  it('sanitizes structured service-log lines', async () => {
    const result = await sanitizeArtifact({
      path: 'log/backend.log',
      kind: 'log',
      bytes: new TextEncoder().encode('{"level":"info","message":"ready"}'),
    }, createSensitiveValueRegistry())

    expect(new TextDecoder().decode(result.bytes)).toContain('"message":"ready"')
  })

  it('redacts request bodies from structured messages and drops nested payload fields', async () => {
    const registry = createSensitiveValueRegistry()
    registry.register(SensitiveValueCategory.CONTROL_TOKEN, 'registered-secret')
    const result = await sanitizeArtifact({
      path: 'log/backend.log',
      kind: 'log',
      bytes: jsonBytes({
        level: 'info',
        message: 'POST /endpoint {"email":"unregistered@example.com"}',
        path: '/roadmaps?token=unregistered',
        headers: { authorization: 'header-secret' },
        payload: { body: 'payload-secret' },
        token: 'registered-secret',
      }),
    }, registry)
    const output = new TextDecoder().decode(result.bytes)

    expect(result.kind).toBe('log')
    expect(output).toContain('[REDACTED:unsafe-log-message]')
    expect(output).toContain('"path":"/roadmaps"')
    expect(output).not.toContain('unregistered@example.com')
    expect(output).not.toContain('header-secret')
    expect(output).not.toContain('payload-secret')
    expect(output).not.toContain('registered-secret')
    expect(output).not.toContain('headers')
    expect(output).not.toContain('payload')
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

  it('rejects an input inside the output directory before publishing', async () => {
    const work = await mkdtemp(join(tmpdir(), 'wren-artifact-overlap-test-'))
    try {
      const output = join(work, 'safe')
      const input = join(output, 'input.json')
      await mkdir(output)
      await writeFile(input, JSON.stringify({ runId: 'run-1' }))

      await expect(sanitizeArtifactFiles([{ path: input, kind: 'attachment' }], output, createSensitiveValueRegistry())).rejects.toThrow('overlap')
      await expect(access(input)).resolves.toBeUndefined()
    } finally {
      await rm(work, { recursive: true, force: true })
    }
  })
})
