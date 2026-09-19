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

const roadmapCard = {
  id: 'roadmap-1',
  published_visibility: 'public',
  status: 'published',
  subject_tags: ['data-structures'],
  title: 'Roadmap',
}

const roadmapNode = {
  description: null,
  effort_estimate: null,
  items: [{ id: 'item-1', text: 'Read', done: false }],
  prereqs: [],
  resources: [{ id: 'resource-1', title: 'Guide', type: 'article', url: 'https://example.com/guide' }],
  subsection_id: 'sub-1',
  tags: ['core'],
  title: 'Hashing',
}

const validStructuredContentByTool: Record<string, Record<string, unknown>> = {
  roadmap_list: { authored: [roadmapCard], followed: [] },
  roadmap_get_profile: { display_name: 'Owner', handle: 'owner', roadmaps: [roadmapCard] },
  roadmap_get: {
    created_at: '2026-01-01T00:00:00Z', description: null, id: 'roadmap-1', owner: 'owner',
    published_visibility: 'public', revision: 2, section_order: ['section-1'], sections: {
      'section-1': { id: 'section-1', subsection_order: ['sub-1'], subsections: {
        'sub-1': { checklist_items: { 'item-1': { id: 'item-1', text: 'Read' } }, description: null, effort_estimate: null,
          id: 'sub-1', item_order: ['item-1'], prereq_ids: [], resource_order: [], resources: {}, tags: ['core'], title: 'Hashing' },
      }, title: 'Foundations' },
    }, status: 'published', subject_tags: ['data-structures'], suggested_path: ['sub-1'], title: 'Roadmap', updated_at: '2026-01-01T00:00:00Z',
  },
  roadmap_get_overview: { details: null, overall: { total_items: 1, checked_items: 0, percent: 0 }, revision: 2, roadmap_id: 'roadmap-1',
    sections: [{ section_id: 'section-1', title: 'Foundations', total_items: 1, checked_items: 0, percent: 0 }], status: 'published', title: 'Roadmap' },
  roadmap_get_next: { complete: false, items: [{ item_id: 'item-1', path_position: 1, resources: [], subsection_id: 'sub-1', text: 'Read', why_now: 'First item' }], remaining_in_path: 1 },
  roadmap_get_node: roadmapNode,
  roadmap_get_section: { include: 'both', next_cursor: null, section_id: 'section-1', steering: null, subsections: [roadmapNode], title: 'Foundations' },
  roadmap_search: { hits: [{ item_id: 'item-1', kind: 'item', matched_tags: null, subsection_id: 'sub-1', title_or_text: 'Read' }] },
  progress_get: { roadmap_id: 'roadmap-1', total_items: 1, checked_items: 0, percent: 0, deadline: null, sections: [], checked_ids: [] },
  progress_update: { progress: { roadmap_id: 'roadmap-1', total_items: 1, checked_items: 1, percent: 100, deadline: null, sections: [], checked_ids: ['item-1'] },
    next: { complete: true, items: [], remaining_in_path: 0 } },
  create_roadmap_draft: { roadmap_id: 'roadmap-1', revision: 1, status: 'draft', remap: {} },
  patch_roadmap_draft: { roadmap_id: 'roadmap-1', revision: 2, changed_nodes: [{ change: 'updated', id: 'sub-1', kind: 'subsection' }], remap: {} },
  replace_roadmap_draft: { roadmap_id: 'roadmap-1', revision: 3, status: 'draft', remap: {} },
  validate_roadmap_draft: { publishable: true, violations: [] },
  publish_roadmap: { roadmap_id: 'roadmap-1', revision: 4, status: 'published' },
  fork_roadmap: { roadmap_id: 'roadmap-2', revision: 1, status: 'draft', source_roadmap_id: 'roadmap-1' },
  edit_roadmap_metadata: { roadmap_id: 'roadmap-1', title: 'Roadmap Updated', description: 'Updated', subject_tags: ['graphs'] },
}

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

  it('projects valid structured content for every registered tool', () => {
    for (const scenario of TOOL_SCENARIO_REGISTRY) {
      const structuredContent = validStructuredContentByTool[scenario.name]
      if (structuredContent === undefined) throw new Error(`missing valid fixture for ${scenario.name}`)
      const output = scenario.projectOutput({ content: [], structuredContent })
      expect(output).toBeDefined()
    }

    const patchOutput = TOOL_SCENARIO_REGISTRY[11].projectOutput({
      content: [],
      structuredContent: validStructuredContentByTool.patch_roadmap_draft,
    })
    expect(patchOutput).toEqual({
      roadmap_id: 'roadmap-1',
      revision: 2,
      changed_nodes: [{ change: 'updated', id: 'sub-1', kind: 'subsection' }],
      remap: {},
    })
  })

  it('asserts requested profile, section, and metadata identities', async () => {
    const baseContext = assertionContext('roadmap-1')
    const context: ToolJourneyContext = {
      ...baseContext,
      state: {
        ...baseContext.state,
        primaryRevision: 1,
        sectionId: 'section-1',
        subsectionIds: ['sub-1'],
        itemIds: ['item-1'],
        toolArguments: {
          roadmap_get_profile: { handle: 'owner' },
          roadmap_get_section: { section_id: 'section-1', include: 'both' },
          edit_roadmap_metadata: { title: 'Roadmap Updated', description: 'Updated', subject_tags: ['graphs'] },
        },
      },
    }

    const profile = TOOL_SCENARIO_REGISTRY[1].projectOutput({ content: [], structuredContent: validStructuredContentByTool.roadmap_get_profile })
    const overview = TOOL_SCENARIO_REGISTRY[3].projectOutput({ content: [], structuredContent: validStructuredContentByTool.roadmap_get_overview })
    const metadata = TOOL_SCENARIO_REGISTRY[16].projectOutput({ content: [], structuredContent: validStructuredContentByTool.edit_roadmap_metadata })
    const patch = TOOL_SCENARIO_REGISTRY[11].projectOutput({ content: [], structuredContent: validStructuredContentByTool.patch_roadmap_draft })

    await TOOL_SCENARIO_REGISTRY[1].assertStableResult(profile, context)
    await TOOL_SCENARIO_REGISTRY[3].assertStableResult(overview, context)
    await TOOL_SCENARIO_REGISTRY[16].assertStableResult(metadata, context)
    await TOOL_SCENARIO_REGISTRY[11].assertStableResult(patch, context)

    const wrongMetadata = { ...metadata, title: 'Wrong title' }
    await expect(Promise.resolve().then(() => TOOL_SCENARIO_REGISTRY[16].assertStableResult(wrongMetadata, context))).rejects.toThrow(
      'metadata title differs from request',
    )
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
