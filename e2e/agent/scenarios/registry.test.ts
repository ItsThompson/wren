import { describe, expect, it, vi } from 'vitest'

import {
  assertToolCoverage,
  compareToolCoverage,
  createToolScenarioRegistry,
  ToolCoverageError,
  TOOL_SCENARIO_REGISTRY,
} from './registry'
import { OAuthScope } from '../types'
import { ToolJourneyName, type ToolJourneyContext, type ToolOutput, type ToolScenario } from './types'

const expectedToolNames = [
  'roadmap_list',
  'roadmap_get_profile',
  'roadmap_get',
  'roadmap_get_overview',
  'roadmap_get_next',
  'roadmap_get_node',
  'roadmap_get_section',
  'roadmap_search',
  'progress_get',
  'progress_update',
  'create_roadmap_draft',
  'patch_roadmap_draft',
  'replace_roadmap_draft',
  'validate_roadmap_draft',
  'publish_roadmap',
  'fork_roadmap',
  'edit_roadmap_metadata',
] as const

const emptyScenario = (name: string): ToolScenario<ToolOutput> => ({
  name,
  journey: ToolJourneyName.STUDY,
  requiredScopes: [],
  call: async () => ({}),
  projectOutput: (output) => output,
  assertStableResult: async () => undefined,
})

function assertionContext(primaryRoadmapId: string | null): ToolJourneyContext {
  const callTool: ToolJourneyContext['agent']['callTool'] = async <TOutput>() => {
    return { content: [], structuredContent: {} } as TOutput
  }
  return {
    agent: {
      authorization: {
        issuer: 'https://api.wren.test',
        clientId: 'client-id',
        clientName: 'client-name',
        grantedScopes: [],
        accessTokenExpiresAtEpochMs: Date.now(),
        hasRefreshToken: true,
      },
      listTools: async () => [],
      callTool,
      waitUntilCurrentAccessTokenExpires: async () => undefined,
      close: async () => undefined,
    },
    restSetup: {
      createAccount: async () => undefined,
      createPublishedRoadmap: async () => 'roadmap-1',
      readRoadmap: async () => ({ id: 'roadmap-1', title: 'Roadmap', status: 'draft', revision: 1 }),
    },
    identity: {
      runId: 'run', testId: 'test', parallelIndex: 0, retry: 0, nonce: 'nonce', resourcePrefix: 'e2etest',
    },
    state: {
      primaryRoadmapId,
      primaryRevision: 2,
      forkedRoadmapId: null,
      ownerHandle: 'owner',
      sectionId: null,
      subsectionIds: [],
      itemIds: [],
    },
  }
}

describe('MCP tool scenario registry', () => {
  it('contains the exact current 17-tool surface', () => {
    expect(TOOL_SCENARIO_REGISTRY.map((scenario) => scenario.name)).toEqual([...expectedToolNames])
    expect(new Set(TOOL_SCENARIO_REGISTRY.map((scenario) => scenario.name)).size).toBe(17)
    expect(Object.isFrozen(TOOL_SCENARIO_REGISTRY)).toBe(true)
    expect(Object.isFrozen(TOOL_SCENARIO_REGISTRY[0])).toBe(true)
  })

  it('declares journey, scopes, output projection, and stable assertion for every entry', () => {
    for (const scenario of TOOL_SCENARIO_REGISTRY) {
      expect([ToolJourneyName.AUTHORING, ToolJourneyName.STUDY]).toContain(scenario.journey)
      expect(scenario.requiredScopes.length).toBeGreaterThan(0)
      expect(typeof scenario.projectOutput).toBe('function')
      expect(typeof scenario.assertStableResult).toBe('function')
      expect(typeof scenario.call).toBe('function')
    }
  })

  it('routes scenario calls through the official client with journey arguments', async () => {
    const agentCalls = vi.fn()
    const callTool: ToolJourneyContext['agent']['callTool'] = async <TOutput>(
      name: string,
      arguments_: Record<string, unknown>,
    ) => {
      agentCalls(name, arguments_)
      return {
        content: [],
        structuredContent: { authored: [], followed: [] },
      } as TOutput
    }
    const context: ToolJourneyContext = {
      agent: {
        authorization: {
          issuer: 'https://api.wren.test',
          clientId: 'client-id',
          clientName: 'client-name',
          grantedScopes: [],
          accessTokenExpiresAtEpochMs: Date.now(),
          hasRefreshToken: true,
        },
        listTools: async () => [],
        callTool,
        waitUntilCurrentAccessTokenExpires: async () => undefined,
        close: async () => undefined,
      },
      restSetup: {
        createAccount: async () => undefined,
        createPublishedRoadmap: async () => 'roadmap-1',
        readRoadmap: async () => ({ id: 'roadmap-1', title: 'Roadmap', status: 'draft', revision: 1 }),
      },
      identity: {
        runId: 'run',
        testId: 'test',
        parallelIndex: 0,
        retry: 0,
        nonce: 'nonce',
        resourcePrefix: 'e2etest',
      },
      state: {
        primaryRoadmapId: null,
        primaryRevision: null,
        forkedRoadmapId: null,
        ownerHandle: 'owner',
        sectionId: null,
        subsectionIds: [],
        itemIds: [],
        toolArguments: { roadmap_list: { include: 'authored' } },
      },
    }
    const scenario = TOOL_SCENARIO_REGISTRY[0]
    expect(scenario.name).toBe('roadmap_list')

    const output = await scenario.call(context)
    await scenario.assertStableResult(output, context)

    expect(output).toEqual({ authored: [], followed: [] })
    expect(agentCalls).toHaveBeenCalledWith('roadmap_list', { include: 'authored' })
  })

  it('rejects a projected result with the wrong roadmap identity', async () => {
    const scenario = TOOL_SCENARIO_REGISTRY[2]
    const output = scenario.projectOutput({
      content: [],
      structuredContent: {
        created_at: '2026-01-01T00:00:00Z',
        description: null,
        id: 'wrong-roadmap',
        owner: 'owner',
        published_visibility: 'public',
        revision: 2,
        section_order: [],
        sections: {},
        status: 'draft',
        subject_tags: [],
        suggested_path: [],
        title: 'Roadmap',
        updated_at: '2026-01-01T00:00:00Z',
      },
    })

    await expect(
      Promise.resolve().then(() => scenario.assertStableResult(output, assertionContext('expected-roadmap'))),
    ).rejects.toThrow('roadmap_id must be expected-roadmap')
  })

  it('rejects missing structured fields for every registered tool', () => {
    for (const scenario of TOOL_SCENARIO_REGISTRY) {
      expect(() => scenario.projectOutput({ content: [], structuredContent: {} })).toThrow('must be')
    }
  })

  it('reports exact sorted missing and unexpected sets', () => {
    const difference = compareToolCoverage(
      ['zeta', 'roadmap_get', 'alpha'],
      [emptyScenario('roadmap_get'), emptyScenario('middle')],
    )

    expect(difference.advertisedWithoutScenario).toEqual(['alpha', 'zeta'])
    expect(difference.scenariosNotAdvertised).toEqual(['middle'])
  })

  it('fails the async coverage gate with sorted missing and unexpected names', async () => {
    const listTools = vi.fn(async () => [
      { name: 'zeta', inputSchema: {} },
      { name: 'roadmap_get', inputSchema: {} },
      { name: 'alpha', inputSchema: {} },
    ])

    await expect(assertToolCoverage({ listTools }, [emptyScenario('roadmap_get'), emptyScenario('middle')])).rejects.toMatchObject({
      difference: {
        advertisedWithoutScenario: ['alpha', 'zeta'],
        scenariosNotAdvertised: ['middle'],
      },
    })
  })

  it('freezes registry scope arrays independently from caller-owned arrays', () => {
    const requiredScopes: OAuthScope[] = [OAuthScope.ROADMAPS_READ]
    const registry = createToolScenarioRegistry([
      {
        ...emptyScenario('roadmap_get'),
        requiredScopes,
      },
    ])

    requiredScopes.push(OAuthScope.ROADMAPS_WRITE)

    expect(registry[0].requiredScopes).toEqual([OAuthScope.ROADMAPS_READ])
    expect(Object.isFrozen(registry[0].requiredScopes)).toBe(true)
  })

  it('reports duplicate registry names explicitly', () => {
    expect(() => createToolScenarioRegistry([emptyScenario('duplicate'), emptyScenario('duplicate')])).toThrowError(
      new ToolCoverageError({
        advertisedWithoutScenario: [],
        scenariosNotAdvertised: [],
        duplicateAdvertisedToolNames: [],
        duplicateScenarioNames: ['duplicate'],
      }),
    )
  })

  it('reports duplicate advertised names explicitly', async () => {
    const listTools = vi.fn(async () => [
      { name: 'roadmap_get', inputSchema: {} },
      { name: 'roadmap_get', inputSchema: {} },
    ])

    await expect(assertToolCoverage({ listTools })).rejects.toMatchObject({
      difference: {
        duplicateAdvertisedToolNames: ['roadmap_get'],
      },
    })
    expect(listTools).toHaveBeenCalledTimes(1)
  })

  it('passes when advertised names exactly match the registry', async () => {
    const listTools = vi.fn(async () => TOOL_SCENARIO_REGISTRY.map((scenario) => ({ name: scenario.name, inputSchema: {} })))

    await expect(assertToolCoverage({ listTools })).resolves.toBeUndefined()
    expect(listTools).toHaveBeenCalledTimes(1)
  })
})
