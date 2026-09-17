import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { operationDomainRegistry, operationRegistry } from './operationRegistry.generated'

const OPENAPI_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'trace'] as const
type OpenApiMethod = (typeof OPENAPI_METHODS)[number]

interface OpenApiOperation {
  operationId: string
  tags?: string[]
}

interface OpenApiDocument {
  paths: Record<string, Partial<Record<OpenApiMethod, OpenApiOperation>>>
}

const domainByTag: Record<string, string> = {
  accounts: 'accounts',
  auth: 'accounts',
  listing: 'accounts',
  onboarding: 'accounts',
  oauth: 'oauth',
  progress: 'progress',
  roadmaps: 'roadmaps',
  skill: 'skill',
}

function readOpenApiDocument(): OpenApiDocument {
  return JSON.parse(readFileSync('openapi.json', 'utf8')) as OpenApiDocument
}

function expectedRegistries(document: OpenApiDocument): {
  operations: Record<string, string>
  domains: Record<string, string>
} {
  const entries: Array<[string, string, string]> = []
  for (const [path, pathItem] of Object.entries(document.paths)) {
    for (const method of OPENAPI_METHODS) {
      const operation = pathItem[method]
      if (!operation) continue
      const tags = operation.tags ?? []
      const [tag] = tags
      const domain = tag === undefined ? undefined : domainByTag[tag]
      if (!operation.operationId) throw new Error(`Missing operationId for ${method.toUpperCase()} ${path}`)
      if (domain === undefined || tags.length !== 1) {
        throw new Error(`Missing browser domain for ${method.toUpperCase()} ${path}`)
      }
      entries.push([`${method.toUpperCase()} ${path}`, operation.operationId, domain])
    }
  }

  entries.sort(([left], [right]) => left.localeCompare(right))
  return {
    operations: Object.fromEntries(entries.map(([key, operationId]) => [key, operationId])),
    domains: Object.fromEntries(entries.map(([key, , domain]) => [key, domain])),
  }
}

describe('generated operation registry', () => {
  it('matches every OpenAPI method, path, operation id, and browser domain exactly', () => {
    const expected = expectedRegistries(readOpenApiDocument())

    expect(operationRegistry).toEqual(expected.operations)
    expect(operationDomainRegistry).toEqual(expected.domains)
  })
})
