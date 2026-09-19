import { getToolScenario, type ExpectedToolName } from './registry'
import type {
  CreateRoadmapDraftOutput,
  DashboardOutput,
  EditRoadmapMetadataOutput,
  ForkRoadmapOutput,
  NextOutput,
  NodeOutput,
  OverviewOutput,
  ProfileOutput,
  ProgressOutput,
  ProgressUpdateOutput,
  PublishRoadmapOutput,
  RoadmapOutput,
  SearchOutput,
  SectionPageOutput,
  ToolJourneyContext,
  ToolOutput,
  PatchRoadmapDraftOutput,
  ReplaceRoadmapDraftOutput,
  ValidateRoadmapDraftOutput,
} from './types'

export function callScenario(
  context: ToolJourneyContext,
  name: 'create_roadmap_draft',
  arguments_: Record<string, unknown>,
): Promise<CreateRoadmapDraftOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_list',
  arguments_: Record<string, unknown>,
): Promise<DashboardOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_get_profile',
  arguments_: Record<string, unknown>,
): Promise<ProfileOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_get_overview',
  arguments_: Record<string, unknown>,
): Promise<OverviewOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_get_next',
  arguments_: Record<string, unknown>,
): Promise<NextOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_get_node',
  arguments_: Record<string, unknown>,
): Promise<NodeOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_get_section',
  arguments_: Record<string, unknown>,
): Promise<SectionPageOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_search',
  arguments_: Record<string, unknown>,
): Promise<SearchOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'roadmap_get',
  arguments_: Record<string, unknown>,
): Promise<RoadmapOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'patch_roadmap_draft',
  arguments_: Record<string, unknown>,
): Promise<PatchRoadmapDraftOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'replace_roadmap_draft',
  arguments_: Record<string, unknown>,
): Promise<ReplaceRoadmapDraftOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'validate_roadmap_draft',
  arguments_: Record<string, unknown>,
): Promise<ValidateRoadmapDraftOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'publish_roadmap',
  arguments_: Record<string, unknown>,
): Promise<PublishRoadmapOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'edit_roadmap_metadata',
  arguments_: Record<string, unknown>,
): Promise<EditRoadmapMetadataOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'fork_roadmap',
  arguments_: Record<string, unknown>,
): Promise<ForkRoadmapOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'progress_get',
  arguments_: Record<string, unknown>,
): Promise<ProgressOutput>
export function callScenario(
  context: ToolJourneyContext,
  name: 'progress_update',
  arguments_: Record<string, unknown>,
): Promise<ProgressUpdateOutput>
export async function callScenario(
  context: ToolJourneyContext,
  name: ExpectedToolName,
  arguments_: Record<string, unknown>,
): Promise<ToolOutput> {
  const scenario = getToolScenario(name)
  context.state.toolArguments = { ...context.state.toolArguments, [name]: arguments_ }
  return scenario.run(context)
}
