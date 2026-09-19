import { describe, expect, it, vi } from 'vitest'

import {
  assertToolCoverage,
  compareToolCoverage,
  createToolScenarioRegistry,
  EXPECTED_TOOL_NAMES,
  ToolCoverageError,
  TOOL_SCENARIO_REGISTRY,
} from './registry'
import { ToolJourneyName, type ToolOutput, type ToolScenario } from './types'

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
