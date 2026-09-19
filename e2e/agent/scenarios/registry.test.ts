import { describe, expect, it, vi } from 'vitest'

import {
  assertToolCoverage,
  compareToolCoverage,
  createToolScenarioRegistry,
  EXPECTED_TOOL_NAMES,
  ToolCoverageError,
  TOOL_SCENARIO_REGISTRY,
} from './registry'
import { ToolJourneyName, type ToolJourneyContext, type ToolOutput, type ToolScenario } from './types'

const emptyScenario = (name: string): ToolScenario<ToolOutput> => ({
  name,
  journey: ToolJourneyName.STUDY,
  requiredScopes: [],
  call: async () => ({}),
  projectOutput: (output) => output,
  assertStableResult: async () => undefined,
})

describe('MCP tool scenario registry', () => {
  it('contains the exact current 17-tool surface', () => {
    expect(TOOL_SCENARIO_REGISTRY.map((scenario) => scenario.name)).toEqual([...EXPECTED_TOOL_NAMES])
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
      return {} as TOutput
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
    const scenario = TOOL_SCENARIO_REGISTRY.find((entry) => entry.name === 'roadmap_list')
    if (scenario === undefined) throw new Error('roadmap_list scenario is missing')

    await scenario.call(context)

    expect(agentCalls).toHaveBeenCalledWith('roadmap_list', { include: 'authored' })
  })

  it('reports exact sorted missing and unexpected sets', () => {
    const difference = compareToolCoverage(
      ['zeta', 'roadmap_get', 'alpha'],
      [emptyScenario('roadmap_get'), emptyScenario('middle')],
    )

    expect(difference.advertisedWithoutScenario).toEqual(['alpha', 'zeta'])
    expect(difference.scenariosNotAdvertised).toEqual(['middle'])
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
