import type { AgentSession, AdvertisedTool, OAuthScope } from '../types'
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

export type ToolOutput = { readonly [key: string]: unknown }
export type ToolOutputProjection<TOutput extends ToolOutput> = (output: TOutput) => TOutput

export interface RoadmapSummaryOutput extends ToolOutput {
  readonly id: string
  readonly title: string
  readonly status: string
  readonly revision?: number
}

export interface RoadmapListOutput extends ToolOutput {
  readonly authored?: readonly RoadmapSummaryOutput[]
  readonly following?: readonly RoadmapSummaryOutput[]
}

export interface RoadmapProfileOutput extends ToolOutput {
  readonly handle: string
  readonly roadmaps?: readonly RoadmapSummaryOutput[]
}

export interface RoadmapGetOutput extends ToolOutput {
  readonly id: string
  readonly title: string
  readonly status: string
  readonly revision: number
  readonly sectionIds?: readonly string[]
  readonly suggestedPath?: readonly string[]
}

export interface RoadmapOverviewOutput extends RoadmapGetOutput {
  readonly progress?: ToolOutput
}

export interface RoadmapNextOutput extends ToolOutput {
  readonly itemIds: readonly string[]
  readonly complete: boolean
  readonly remainingInPath: number
}

export interface RoadmapNodeOutput extends ToolOutput {
  readonly subsectionId: string
  readonly title: string
  readonly itemIds: readonly string[]
}

export interface RoadmapSectionOutput extends ToolOutput {
  readonly sectionId: string
  readonly subsectionIds: readonly string[]
}

export interface RoadmapSearchOutput extends ToolOutput {
  readonly hits: readonly ToolOutput[]
}

export interface ProgressGetOutput extends ToolOutput {
  readonly roadmapId: string
  readonly checkedItems: number
  readonly percent: number
  readonly checkedIds: readonly string[]
}

export interface ProgressUpdateOutput extends ProgressGetOutput {
  readonly next?: RoadmapNextOutput
}

export interface RoadmapMutationOutput extends ToolOutput {
  readonly roadmapId: string
  readonly revision: number
  readonly status: string
}

export interface CreateRoadmapDraftOutput extends RoadmapMutationOutput {
  readonly remap?: ToolOutput
}

export interface PatchRoadmapDraftOutput extends RoadmapMutationOutput {
  readonly changedNodeIds?: readonly string[]
}

export interface ReplaceRoadmapDraftOutput extends RoadmapMutationOutput {
  readonly remap?: ToolOutput
}

export interface ValidateRoadmapDraftOutput extends ToolOutput {
  readonly publishable: boolean
  readonly violations: readonly ToolOutput[]
}

export interface PublishRoadmapOutput extends RoadmapMutationOutput {}

export interface ForkRoadmapOutput extends RoadmapMutationOutput {
  readonly sourceRoadmapId: string
}

export interface EditRoadmapMetadataOutput extends ToolOutput {
  readonly roadmapId: string
  readonly title: string
  readonly description?: string
  readonly subjectTags?: readonly string[]
}

export interface ToolScenario<TOutput extends ToolOutput> {
  readonly name: string
  readonly journey: ToolJourneyName
  readonly requiredScopes: readonly OAuthScope[]
  readonly call: (context: ToolJourneyContext) => Promise<TOutput>
  projectOutput(output: TOutput): TOutput
  assertStableResult(output: TOutput, context: ToolJourneyContext): Promise<void>
}

export interface ToolCoverageDifference {
  readonly advertisedWithoutScenario: readonly string[]
  readonly scenariosNotAdvertised: readonly string[]
  readonly duplicateAdvertisedToolNames: readonly string[]
  readonly duplicateScenarioNames: readonly string[]
}

export type AdvertisedToolList = readonly AdvertisedTool[]
