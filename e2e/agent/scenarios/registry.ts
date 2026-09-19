import { OAuthScope, type AgentSession, type AdvertisedTool } from '../types'
import {
  type CreateRoadmapDraftOutput,
  type EditRoadmapMetadataOutput,
  type ForkRoadmapOutput,
  type PatchRoadmapDraftOutput,
  type ProgressGetOutput,
  type ProgressUpdateOutput,
  type PublishRoadmapOutput,
  type ReplaceRoadmapDraftOutput,
  type RoadmapGetOutput,
  type RoadmapOverviewOutput,
  type RoadmapListOutput,
  type RoadmapNextOutput,
  type RoadmapNodeOutput,
  type RoadmapProfileOutput,
  type RoadmapSearchOutput,
  type RoadmapSectionOutput,
  type ToolCoverageDifference,
  type ToolJourneyContext,
  ToolJourneyName,
  type ToolOutput,
  type ToolScenario,
  type ValidateRoadmapDraftOutput,
} from './types'

export const EXPECTED_TOOL_NAMES = Object.freeze([
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
] as const)

export type ExpectedToolName = (typeof EXPECTED_TOOL_NAMES)[number]

export class ToolCoverageError extends Error {
  readonly difference: ToolCoverageDifference

  constructor(difference: ToolCoverageDifference) {
    super(formatCoverageDifference(difference))
    this.name = 'ToolCoverageError'
    this.difference = difference
  }
}

function deferredCall<TOutput extends ToolOutput>(name: string): (context: ToolJourneyContext) => Promise<TOutput> {
  return async (_context: ToolJourneyContext): Promise<TOutput> => {
    throw new Error(`tool scenario ${name} has no journey binding`)
  }
}

function identityProjection<TOutput extends ToolOutput>(output: TOutput): TOutput {
  return output
}

async function assertNonEmptyOutput<TOutput extends ToolOutput>(
  output: TOutput,
  _context: ToolJourneyContext,
): Promise<void> {
  if (Object.keys(output).length === 0) throw new Error('tool scenario returned an empty output projection')
}

function createScenario<TOutput extends ToolOutput>(
  name: ExpectedToolName,
  journey: ToolJourneyName,
  requiredScopes: readonly OAuthScope[],
): ToolScenario<TOutput> {
  return Object.freeze({
    name,
    journey,
    requiredScopes: Object.freeze([...requiredScopes]),
    call: deferredCall<TOutput>(name),
    projectOutput: identityProjection,
    assertStableResult: assertNonEmptyOutput,
  })
}

export function createToolScenarioRegistry<T extends readonly ToolScenario<ToolOutput>[]>(
  entries: T,
): readonly T[number][] {
  const names = entries.map((entry) => entry.name)
  const duplicateScenarioNames = duplicateNames(names)
  if (duplicateScenarioNames.length > 0) {
    throw new ToolCoverageError({
      advertisedWithoutScenario: [],
      scenariosNotAdvertised: [],
      duplicateAdvertisedToolNames: [],
      duplicateScenarioNames,
    })
  }
  return Object.freeze(entries.map((entry) => Object.freeze(entry)))
}

export const TOOL_SCENARIO_REGISTRY = createToolScenarioRegistry([
  createScenario<RoadmapListOutput>('roadmap_list', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapProfileOutput>('roadmap_get_profile', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapGetOutput>('roadmap_get', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapOverviewOutput>('roadmap_get_overview', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapNextOutput>('roadmap_get_next', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapNodeOutput>('roadmap_get_node', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapSectionOutput>('roadmap_get_section', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<RoadmapSearchOutput>('roadmap_search', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<ProgressGetOutput>('progress_get', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ]),
  createScenario<ProgressUpdateOutput>('progress_update', ToolJourneyName.STUDY, [OAuthScope.PROGRESS_WRITE]),
  createScenario<CreateRoadmapDraftOutput>('create_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
  createScenario<PatchRoadmapDraftOutput>('patch_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
  createScenario<ReplaceRoadmapDraftOutput>('replace_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
  createScenario<ValidateRoadmapDraftOutput>('validate_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
  createScenario<PublishRoadmapOutput>('publish_roadmap', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
  createScenario<ForkRoadmapOutput>('fork_roadmap', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
  createScenario<EditRoadmapMetadataOutput>('edit_roadmap_metadata', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE]),
] as const)

export function compareToolCoverage(
  advertisedTools: readonly AdvertisedTool[] | readonly string[],
  registry: readonly ToolScenario<ToolOutput>[] = TOOL_SCENARIO_REGISTRY,
): ToolCoverageDifference {
  const advertisedNames = advertisedTools.map((tool) => (typeof tool === 'string' ? tool : tool.name))
  const scenarioNames = registry.map((scenario) => scenario.name)
  const advertisedSet = new Set(advertisedNames)
  const scenarioSet = new Set(scenarioNames)

  return {
    advertisedWithoutScenario: sortedNames([...advertisedSet].filter((name) => !scenarioSet.has(name))),
    scenariosNotAdvertised: sortedNames([...scenarioSet].filter((name) => !advertisedSet.has(name))),
    duplicateAdvertisedToolNames: duplicateNames(advertisedNames),
    duplicateScenarioNames: duplicateNames(scenarioNames),
  }
}

export async function assertToolCoverage(
  agent: Pick<AgentSession, 'listTools'>,
  registry: readonly ToolScenario<ToolOutput>[] = TOOL_SCENARIO_REGISTRY,
): Promise<void> {
  const advertisedTools = await agent.listTools()
  const difference = compareToolCoverage(advertisedTools, registry)
  if (
    difference.advertisedWithoutScenario.length > 0 ||
    difference.scenariosNotAdvertised.length > 0 ||
    difference.duplicateAdvertisedToolNames.length > 0 ||
    difference.duplicateScenarioNames.length > 0
  ) {
    throw new ToolCoverageError(difference)
  }
}

function duplicateNames(names: readonly string[]): string[] {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const name of names) {
    if (seen.has(name)) duplicates.add(name)
    seen.add(name)
  }
  return sortedNames([...duplicates])
}

function sortedNames(names: readonly string[]): string[] {
  return [...names].sort((left, right) => left.localeCompare(right))
}

function formatCoverageDifference(difference: ToolCoverageDifference): string {
  const lines = ['MCP tool coverage mismatch']
  if (difference.advertisedWithoutScenario.length > 0) {
    lines.push(`missing scenarios: ${difference.advertisedWithoutScenario.join(', ')}`)
  }
  if (difference.scenariosNotAdvertised.length > 0) {
    lines.push(`unexpected scenarios: ${difference.scenariosNotAdvertised.join(', ')}`)
  }
  if (difference.duplicateAdvertisedToolNames.length > 0) {
    lines.push(`duplicate advertised names: ${difference.duplicateAdvertisedToolNames.join(', ')}`)
  }
  if (difference.duplicateScenarioNames.length > 0) {
    lines.push(`duplicate registry names: ${difference.duplicateScenarioNames.join(', ')}`)
  }
  return lines.join('; ')
}
