import { OAuthScope, type AgentSession } from '../types'
import {
  type CreateRoadmapDraftOutput,
  type EditRoadmapMetadataOutput,
  type ForkRoadmapOutput,
  type ProgressOutput,
  type PublishRoadmapOutput,
  type RoadmapOutput,
  type ToolJourneyContext,
  type ToolOutput,
  type ToolScenario,
  type PatchRoadmapDraftOutput,
  type ReplaceRoadmapDraftOutput,
  type ValidateRoadmapDraftOutput,
} from './types'
import { TOOL_SCENARIO_REGISTRY } from './registry'
import {
  assertRoadmapSnapshot,
  assertSubsectionTitle,
  buildAuthoringRoadmap,
  buildReplacementRoadmap,
  collectNodeIds,
  resolveRoadmapIds,
  structureSnapshot,
} from './authoring-fixture'

export type { AuthoringRoadmapDraft } from './authoring-fixture'

export interface AuthoringJourneyResult {
  readonly create: CreateRoadmapDraftOutput
  readonly initialRead: RoadmapOutput
  readonly patch: PatchRoadmapDraftOutput
  readonly patchedRead: RoadmapOutput
  readonly replace: ReplaceRoadmapDraftOutput
  readonly replacedRead: RoadmapOutput
  readonly validation: ValidateRoadmapDraftOutput
  readonly publish: PublishRoadmapOutput
  readonly publishedRead: RoadmapOutput
  readonly metadata: EditRoadmapMetadataOutput
  readonly metadataRead: RoadmapOutput
  readonly fork: ForkRoadmapOutput
  readonly forkRead: RoadmapOutput
  readonly forkProgress: ProgressOutput
}

export {
  assertRoadmapSnapshot,
  assertSubsectionTitle,
  buildAuthoringRoadmap,
  buildReplacementRoadmap,
  collectNodeIds,
  resolveRoadmapIds,
  structureSnapshot,
} from './authoring-fixture'

export async function runAuthoringJourney(
  context: ToolJourneyContext,
  roadmapIdentity: {
    readonly title: string
    readonly proposedIdPrefix: string
    readonly itemIds: readonly string[]
  },
): Promise<AuthoringJourneyResult> {
  const initialRoadmap = buildAuthoringRoadmap(roadmapIdentity)
  const replacementRoadmap = buildReplacementRoadmap(roadmapIdentity)
  const create = await callScenario<CreateRoadmapDraftOutput>(context, 'create_roadmap_draft', { roadmap: initialRoadmap })
  context.state.primaryRoadmapId = create.roadmap_id
  context.state.primaryRevision = create.revision
  const resolvedIds = resolveRoadmapIds(roadmapIdentity, create.remap)
  context.state.sectionId = resolvedIds.sectionId
  context.state.subsectionIds = resolvedIds.subsectionIds
  context.state.itemIds = resolvedIds.itemIds

  const initialRead = await readRoadmap(context, create.roadmap_id)
  assertRoadmapSnapshot(initialRead, {
    id: create.roadmap_id,
    title: roadmapIdentity.title,
    status: 'draft',
    revision: create.revision,
    sectionId: resolvedIds.sectionId,
    subsectionIds: resolvedIds.subsectionIds,
  })

  const patch = await callScenario<PatchRoadmapDraftOutput>(context, 'patch_roadmap_draft', {
    roadmap_id: create.roadmap_id,
    revision: requireRevision(context),
    operations: [
      {
        op: 'update_subsection',
        subsection_id: resolvedIds.subsectionIds[0],
        title: 'Arrays and strings',
      },
      {
        op: 'set_tags',
        subsection_id: resolvedIds.subsectionIds[0],
        tags: ['foundations', 'arrays'],
      },
    ],
  })
  context.state.primaryRevision = patch.revision
  const patchedRead = await readRoadmap(context, create.roadmap_id)
  assertRoadmapSnapshot(patchedRead, {
    id: create.roadmap_id,
    title: roadmapIdentity.title,
    status: 'draft',
    revision: patch.revision,
    sectionId: resolvedIds.sectionId,
    subsectionIds: resolvedIds.subsectionIds,
  })
  assertSubsectionTitle(patchedRead, resolvedIds.subsectionIds[0], 'Arrays and strings')

  const replace = await callScenario<ReplaceRoadmapDraftOutput>(context, 'replace_roadmap_draft', {
    roadmap_id: create.roadmap_id,
    full_document: replacementRoadmap,
  })
  context.state.primaryRevision = replace.revision
  const replacedRead = await readRoadmap(context, create.roadmap_id)
  assertRoadmapSnapshot(replacedRead, {
    id: create.roadmap_id,
    title: roadmapIdentity.title,
    status: 'draft',
    revision: replace.revision,
    sectionId: resolvedIds.sectionId,
    subsectionIds: resolvedIds.subsectionIds,
  })
  assertSubsectionTitle(replacedRead, resolvedIds.subsectionIds[1], 'Hash tables')

  const validation = await callScenario<ValidateRoadmapDraftOutput>(context, 'validate_roadmap_draft', {
    roadmap_id: create.roadmap_id,
  })
  if (!validation.publishable || validation.violations.length !== 0) {
    throw new Error('authoring fixture must validate as publishable')
  }

  const publish = await callScenario<PublishRoadmapOutput>(context, 'publish_roadmap', {
    roadmap_id: create.roadmap_id,
  })
  context.state.primaryRevision = publish.revision
  const publishedRead = await readRoadmap(context, create.roadmap_id)
  assertRoadmapSnapshot(publishedRead, {
    id: create.roadmap_id,
    title: roadmapIdentity.title,
    status: 'published',
    revision: publish.revision,
    sectionId: resolvedIds.sectionId,
    subsectionIds: resolvedIds.subsectionIds,
  })
  const structureBeforeMetadata = structureSnapshot(publishedRead)

  const metadataRequest = {
    roadmap_id: create.roadmap_id,
    title: `${roadmapIdentity.title} Published`,
    description: 'Metadata edited through the official client.',
    subject_tags: ['algorithms', 'authoring'],
  }
  const metadata = await callScenario<EditRoadmapMetadataOutput>(context, 'edit_roadmap_metadata', metadataRequest)
  const metadataRead = await readRoadmap(context, create.roadmap_id)
  if (
    metadataRead.title !== metadataRequest.title ||
    metadataRead.description !== metadataRequest.description ||
    JSON.stringify(metadataRead.subject_tags) !== JSON.stringify(metadataRequest.subject_tags)
  ) {
    throw new Error('metadata read-back does not match the official-client write')
  }
  if (JSON.stringify(structureSnapshot(metadataRead)) !== JSON.stringify(structureBeforeMetadata)) {
    throw new Error('metadata edit changed structural roadmap content')
  }

  const fork = await callScenario<ForkRoadmapOutput>(context, 'fork_roadmap', {
    source_roadmap_id: create.roadmap_id,
  })
  context.state.forkedRoadmapId = fork.roadmap_id
  const forkRead = await readRoadmapAsFork(context, fork.roadmap_id)
  const forkIds = collectNodeIds(forkRead)
  const sourceIds = collectNodeIds(publishedRead)
  for (const id of forkIds) {
    if (sourceIds.has(id)) throw new Error('fork must mint fresh node identities')
  }
  if (forkRead.status !== 'draft' || forkRead.revision !== 1) throw new Error('fork must be a fresh draft')

  const forkProgress = await readForkProgress(context, fork.roadmap_id)
  if (forkProgress.checked_items !== 0 || (forkProgress.checked_ids !== null && forkProgress.checked_ids.length !== 0)) {
    throw new Error('fork must not carry source progress')
  }

  return {
    create,
    initialRead,
    patch,
    patchedRead,
    replace,
    replacedRead,
    validation,
    publish,
    publishedRead,
    metadata,
    metadataRead,
    fork,
    forkRead,
    forkProgress,
  }
}

async function readRoadmap(context: ToolJourneyContext, roadmapId: string): Promise<RoadmapOutput> {
  return callScenario<RoadmapOutput>(context, 'roadmap_get', { roadmap_id: roadmapId })
}

async function readRoadmapAsFork(context: ToolJourneyContext, roadmapId: string): Promise<RoadmapOutput> {
  const sourceState = context.state
  context.state = {
    ...sourceState,
    primaryRoadmapId: roadmapId,
    primaryRevision: 1,
    sectionId: null,
    subsectionIds: [],
    itemIds: [],
  }
  try {
    return await readRoadmap(context, roadmapId)
  } finally {
    context.state = sourceState
  }
}

async function readForkProgress(context: ToolJourneyContext, roadmapId: string): Promise<ProgressOutput> {
  const sourceState = context.state
  context.state = { ...sourceState, primaryRoadmapId: roadmapId, primaryRevision: 1 }
  try {
    return await callScenario<ProgressOutput>(context, 'progress_get', { roadmap_id: roadmapId, detailed: true })
  } finally {
    context.state = sourceState
  }
}

async function callScenario<TOutput extends ToolOutput>(
  context: ToolJourneyContext,
  name: string,
  arguments_: Record<string, unknown>,
): Promise<TOutput> {
  const scenario = findScenario<TOutput>(name)
  context.state.toolArguments = { ...context.state.toolArguments, [name]: arguments_ }
  const output = await scenario.call(context)
  await scenario.assertStableResult(output, context)
  return output
}

function findScenario<TOutput extends ToolOutput>(name: string): ToolScenario<TOutput> {
  const scenario = TOOL_SCENARIO_REGISTRY.find((candidate) => candidate.name === name)
  if (scenario === undefined) throw new Error(`missing authoring scenario ${name}`)
  return scenario as unknown as ToolScenario<TOutput>
}

function requireRevision(context: ToolJourneyContext): number {
  if (context.state.primaryRevision === null) throw new Error('authoring journey has no current roadmap revision')
  return context.state.primaryRevision
}

export function createAuthoringContext(
  agent: AgentSession,
  identity: ToolJourneyContext['identity'],
  ownerHandle: string,
): ToolJourneyContext {
  return {
    agent,
    restSetup: {
      createAccount: async () => undefined,
      createPublishedRoadmap: async () => {
        throw new Error('authoring journey does not seed roadmaps through REST')
      },
      readRoadmap: async () => {
        throw new Error('authoring journey reads roadmaps through the official client')
      },
    },
    identity,
    state: {
      primaryRoadmapId: null,
      primaryRevision: null,
      forkedRoadmapId: null,
      ownerHandle,
      sectionId: null,
      subsectionIds: [],
      itemIds: [],
      toolArguments: {},
    },
  }
}

export function authoringScopes(): readonly OAuthScope[] {
  return [OAuthScope.ROADMAPS_READ, OAuthScope.ROADMAPS_WRITE]
}
