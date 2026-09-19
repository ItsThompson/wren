import { OAuthScope, type AgentSession, type AdvertisedTool } from '../types'
import {
  type CreateRoadmapDraftOutput,
  type DashboardOutput,
  type EditRoadmapMetadataOutput,
  type ForkRoadmapOutput,
  type McpCallToolResult,
  type NextOutput,
  type NodeOutput,
  type OverviewOutput,
  type PatchRoadmapDraftOutput,
  type ProgressOutput,
  type ProgressUpdateOutput,
  type PublishRoadmapOutput,
  type ReplaceRoadmapDraftOutput,
  type ProfileOutput,
  type RoadmapOutput,
  type SearchOutput,
  type SectionPageOutput,
  type ToolCoverageDifference,
  type ToolJourneyContext,
  ToolJourneyName,
  type ToolOutput,
  type ToolScenario,
  type ValidateRoadmapDraftOutput,
} from './types'
import {
  projectDashboard,
  projectNext,
  projectNode,
  projectOverview,
  projectProgress,
  projectProgressUpdate,
  projectProfile,
  projectRoadmap,
  projectSearch,
  projectSection,
} from './projections'
import {
  projectCreate,
  projectFork,
  projectMetadata,
  projectPatch,
  projectPublish,
  projectReplace,
  projectValidate,
} from './write-projections'
import {
  assertCreate,
  assertDashboard,
  assertFork,
  assertMetadata,
  assertNext,
  assertNode,
  assertOverview,
  assertPatch,
  assertProfile,
  assertProgress,
  assertProgressUpdate,
  assertPublish,
  assertReplace,
  assertRoadmap,
  assertSearch,
  assertSection,
  assertValidate,
} from './assertions'

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

function liveCall<TOutput extends ToolOutput>(
  name: string,
  projectOutput: (result: McpCallToolResult) => TOutput,
): (context: ToolJourneyContext) => Promise<TOutput> {
  return async (context: ToolJourneyContext): Promise<TOutput> => {
    const arguments_ = context.state.toolArguments?.[name]
    if (arguments_ === undefined) throw new Error(`tool scenario ${name} has no journey arguments`)
    const result = await context.agent.callTool<McpCallToolResult>(name, arguments_)
    return projectOutput(result)
  }
}

function createScenario<TOutput extends ToolOutput>(
  name: ExpectedToolName,
  journey: ToolJourneyName,
  requiredScopes: readonly OAuthScope[],
  projectOutput: (result: McpCallToolResult) => TOutput,
  assertStableResult: (output: TOutput, context: ToolJourneyContext) => Promise<void>,
): ToolScenario<TOutput> {
  return Object.freeze({
    name,
    journey,
    requiredScopes: Object.freeze([...requiredScopes]),
    call: liveCall<TOutput>(name, projectOutput),
    projectOutput,
    assertStableResult,
  })
}

export function createToolScenarioRegistry<T extends readonly ToolScenario<ToolOutput>[]>(
  entries: T,
): Readonly<T> {
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
  return Object.freeze(
    entries.map((entry) =>
      Object.freeze({
        ...entry,
        requiredScopes: Object.freeze([...entry.requiredScopes]),
      }),
    ),
  ) as unknown as Readonly<T>
}

export const TOOL_SCENARIO_REGISTRY = createToolScenarioRegistry([
  createScenario<DashboardOutput>('roadmap_list', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectDashboard, assertDashboard),
  createScenario<ProfileOutput>('roadmap_get_profile', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectProfile, assertProfile),
  createScenario<RoadmapOutput>('roadmap_get', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_READ], projectRoadmap, assertRoadmap),
  createScenario<OverviewOutput>('roadmap_get_overview', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectOverview, assertOverview),
  createScenario<NextOutput>('roadmap_get_next', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectNext, assertNext),
  createScenario<NodeOutput>('roadmap_get_node', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectNode, assertNode),
  createScenario<SectionPageOutput>('roadmap_get_section', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectSection, assertSection),
  createScenario<SearchOutput>('roadmap_search', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectSearch, assertSearch),
  createScenario<ProgressOutput>('progress_get', ToolJourneyName.STUDY, [OAuthScope.ROADMAPS_READ], projectProgress, assertProgress),
  createScenario<ProgressUpdateOutput>('progress_update', ToolJourneyName.STUDY, [OAuthScope.PROGRESS_WRITE], projectProgressUpdate, assertProgressUpdate),
  createScenario<CreateRoadmapDraftOutput>('create_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectCreate, assertCreate),
  createScenario<PatchRoadmapDraftOutput>('patch_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectPatch, assertPatch),
  createScenario<ReplaceRoadmapDraftOutput>('replace_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectReplace, assertReplace),
  createScenario<ValidateRoadmapDraftOutput>('validate_roadmap_draft', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectValidate, assertValidate),
  createScenario<PublishRoadmapOutput>('publish_roadmap', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectPublish, assertPublish),
  createScenario<ForkRoadmapOutput>('fork_roadmap', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectFork, assertFork),
  createScenario<EditRoadmapMetadataOutput>('edit_roadmap_metadata', ToolJourneyName.AUTHORING, [OAuthScope.ROADMAPS_WRITE], projectMetadata, assertMetadata),
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
