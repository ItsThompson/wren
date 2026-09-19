import type { AgentSession, OAuthScope } from '../types'
import type { TestAttemptIdentity } from '../../fixtures/attempt-identity'

export enum ToolJourneyName {
  AUTHORING = 'authoring',
  STUDY = 'study',
}

export interface ToolJourneyState {
  primaryRoadmapId: string | null
  primaryRevision: number | null
  forkedRoadmapId: string | null
  ownerHandle: string
  sectionId: string | null
  subsectionIds: readonly string[]
  itemIds: readonly string[]
  toolArguments?: Readonly<Record<string, Readonly<Record<string, unknown>>>>
}

export interface RestSetup {
  createAccount(account: { username: string; email: string; password: string }): Promise<void>
  createPublishedRoadmap(owner: { username: string; email: string; password: string }, fixture: {
    title: string
    proposedIdPrefix: string
    itemIds: readonly string[]
  }): Promise<string>
  readRoadmap(roadmapId: string): Promise<{
    id: string
    title: string
    status: string
    revision: number
  }>
}

export interface ToolJourneyContext {
  agent: AgentSession
  restSetup: RestSetup
  identity: TestAttemptIdentity
  state: ToolJourneyState
}

export interface McpCallToolResult {
  readonly content: readonly McpContentBlock[]
  readonly isError?: boolean
  readonly structuredContent?: unknown
}

export interface McpContentBlock {
  readonly type: string
  readonly text?: string
}

export interface RoadmapCardOutput {
  readonly id: string
  readonly published_visibility: string
  readonly status: string
  readonly subject_tags: readonly string[]
  readonly title: string
}

export interface DashboardOutput {
  readonly authored: readonly RoadmapCardOutput[]
  readonly followed: readonly RoadmapCardOutput[]
}

export interface ProfileOutput {
  readonly display_name: string
  readonly handle: string
  readonly roadmaps: readonly RoadmapCardOutput[]
}

export interface RoadmapChecklistItemOutput {
  readonly id: string
  readonly text: string
}
export interface RoadmapResourceOutput {
  readonly id: string
  readonly title: string
  readonly type: string
  readonly url: string
}

export interface RoadmapSubsectionOutput {
  readonly checklist_items: Readonly<Record<string, RoadmapChecklistItemOutput>>
  readonly description: string | null
  readonly effort_estimate: string | null
  readonly id: string
  readonly item_order: readonly string[]
  readonly prereq_ids: readonly string[]
  readonly resource_order: readonly string[]
  readonly resources: Readonly<Record<string, RoadmapResourceOutput>>
  readonly tags: readonly string[]
  readonly title: string
}

export interface RoadmapSectionDocumentOutput {
  readonly id: string
  readonly subsection_order: readonly string[]
  readonly subsections: Readonly<Record<string, RoadmapSubsectionOutput>>
  readonly title: string
}

export interface RoadmapOutput {
  readonly created_at: string
  readonly description: string | null
  readonly id: string
  readonly owner: string
  readonly published_visibility: string
  readonly revision: number
  readonly section_order: readonly string[]
  readonly sections: Readonly<Record<string, RoadmapSectionDocumentOutput>>
  readonly status: string
  readonly subject_tags: readonly string[]
  readonly suggested_path: readonly string[]
  readonly title: string
  readonly updated_at: string
}

export interface SectionOverviewOutput {
  readonly section_id: string
  readonly title: string
  readonly total_items: number
  readonly checked_items: number
  readonly percent: number
}

export interface OverallProgressOutput {
  readonly total_items: number
  readonly checked_items: number
  readonly percent: number
}

export interface OverviewDetailsOutput {
  readonly owner: string
  readonly description: string | null
  readonly subject_tags: readonly string[]
  readonly published_visibility: string
  readonly created_at: string
  readonly updated_at: string
  readonly suggested_path: readonly string[]
}

export interface OverviewOutput {
  readonly details: OverviewDetailsOutput | null
  readonly overall: OverallProgressOutput
  readonly revision: number
  readonly roadmap_id: string
  readonly sections: readonly SectionOverviewOutput[]
  readonly status: string
  readonly title: string
}

export interface ResourceLinkOutput {
  readonly title: string
  readonly url: string
  readonly type: string
}

export interface NextItemOutput {
  readonly item_id: string
  readonly path_position: number | null
  readonly resources: readonly ResourceLinkOutput[]
  readonly subsection_id: string
  readonly text: string
  readonly why_now: string
}

export interface NextOutput {
  readonly complete: boolean
  readonly items: readonly NextItemOutput[]
  readonly remaining_in_path: number
}

export interface ItemStateOutput {
  readonly id: string
  readonly text: string
  readonly done: boolean
}

export interface PrereqOutput {
  readonly id: string
  readonly title: string
  readonly done: boolean
}

export interface ResourceOutput extends ResourceLinkOutput {
  readonly id: string
}

export interface NodeOutput {
  readonly description: string | null
  readonly effort_estimate: string | null
  readonly items: readonly ItemStateOutput[]
  readonly prereqs: readonly PrereqOutput[]
  readonly resources: readonly ResourceOutput[]
  readonly subsection_id: string
  readonly tags: readonly string[]
  readonly title: string
}

export interface SectionPageOutput {
  readonly include: string
  readonly next_cursor: string | null
  readonly section_id: string
  readonly steering: string | null
  readonly subsections: readonly NodeOutput[]
  readonly title: string
}

export interface SearchHitOutput {
  readonly item_id: string | null
  readonly kind: string
  readonly matched_tags: readonly string[] | null
  readonly subsection_id: string
  readonly title_or_text: string
}

export interface SearchOutput {
  readonly hits: readonly SearchHitOutput[]
}

export interface SectionProgressOutput {
  readonly section_id: string
  readonly total_items: number
  readonly checked_items: number
  readonly percent: number
}

export interface ProgressOutput {
  readonly roadmap_id: string
  readonly total_items: number
  readonly checked_items: number
  readonly percent: number
  readonly deadline: string | null
  readonly sections: readonly SectionProgressOutput[]
  readonly checked_ids: readonly string[] | null
}

export interface ProgressUpdateOutput {
  readonly progress: ProgressOutput
  readonly next: NextOutput
}

export interface RoadmapMutationOutput {
  readonly roadmap_id: string
  readonly revision: number
  readonly status: string
}

export interface CreateRoadmapDraftOutput extends RoadmapMutationOutput {
  readonly remap: Readonly<Record<string, string>>
}

export interface ChangedNodeOutput {
  readonly change: string
  readonly id: string
  readonly kind: string
}

export interface PatchRoadmapDraftOutput {
  readonly roadmap_id: string
  readonly revision: number
  readonly changed_nodes: readonly ChangedNodeOutput[]
  readonly remap: Readonly<Record<string, string>>
}

export interface ReplaceRoadmapDraftOutput extends RoadmapMutationOutput {
  readonly remap: Readonly<Record<string, string>>
}

export interface ViolationOutput {
  readonly ids: readonly string[]
  readonly message: string
  readonly rule: string
}

export interface ValidateRoadmapDraftOutput {
  readonly publishable: boolean
  readonly violations: readonly ViolationOutput[]
}

export type PublishRoadmapOutput = RoadmapMutationOutput

export interface ForkRoadmapOutput extends RoadmapMutationOutput {
  readonly source_roadmap_id: string
}

export interface EditRoadmapMetadataOutput {
  readonly roadmap_id: string
  readonly title: string
  readonly description: string | null
  readonly subject_tags: readonly string[]
}

export type ToolOutput = object

export interface ToolScenario<TOutput extends ToolOutput> {
  readonly name: string
  readonly journey: ToolJourneyName
  readonly requiredScopes: readonly OAuthScope[]
  readonly call: (context: ToolJourneyContext) => Promise<TOutput>
  readonly projectOutput: (output: McpCallToolResult) => TOutput
  readonly assertStableResult: (output: TOutput, context: ToolJourneyContext) => Promise<void>
}

export interface ToolCoverageDifference {
  readonly advertisedWithoutScenario: readonly string[]
  readonly scenariosNotAdvertised: readonly string[]
  readonly duplicateAdvertisedToolNames: readonly string[]
  readonly duplicateScenarioNames: readonly string[]
}

