import {
  type CreateRoadmapDraftOutput,
  type EditRoadmapMetadataOutput,
  type ForkRoadmapOutput,
  type ProgressOutput,
  type ProgressUpdateOutput,
  type PublishRoadmapOutput,
  type RoadmapOutput,
  type ToolJourneyContext,
  type PatchRoadmapDraftOutput,
  type ReplaceRoadmapDraftOutput,
  type ValidateRoadmapDraftOutput,
} from './types'
import { callScenario } from './scenario-runner'
import {
  assertBoundedRemap,
  assertRoadmapSnapshot,
  assertSubsectionItemIds,
  assertSubsectionTags,
  assertSubsectionTitle,
  buildAuthoringRoadmap,
  buildReplacementRoadmap,
  collectNodeIds,
  resolveRoadmapIds,
  structureSnapshot,
} from './authoring-fixture'

export type { AuthoringRoadmapDraft } from './authoring-fixture'
export { createAuthoringContext, authoringScopes } from './authoring-context'

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
  readonly sourceProgressUpdate: ProgressUpdateOutput
  readonly sourceProgress: ProgressOutput
  readonly fork: ForkRoadmapOutput
  readonly forkRead: RoadmapOutput
  readonly forkProgress: ProgressOutput
}

export {
  assertBoundedRemap,
  assertRoadmapSnapshot,
  assertSubsectionItemIds,
  assertSubsectionTags,
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
  const create = await callScenario(context, 'create_roadmap_draft', { roadmap: initialRoadmap })
  assertBoundedRemap(create.remap, initialRoadmap)
  context.state.primaryRoadmapId = create.roadmap_id
  context.state.primaryRevision = create.revision
  let resolvedIds = resolveRoadmapIds(roadmapIdentity, create.remap)
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
  assertSubsectionItemIds(initialRead, resolvedIds.subsectionIds[0], resolvedIds.itemIds.slice(0, 2))
  assertSubsectionItemIds(initialRead, resolvedIds.subsectionIds[1], [resolvedIds.itemIds[2]])

  const patch = await callScenario(context, 'patch_roadmap_draft', {
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
  assertBoundedRemap(patch.remap, initialRoadmap)
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
  assertSubsectionTags(patchedRead, resolvedIds.subsectionIds[0], ['foundations', 'arrays'])

  const replace = await callScenario(context, 'replace_roadmap_draft', {
    roadmap_id: create.roadmap_id,
    full_document: replacementRoadmap,
  })
  assertBoundedRemap(replace.remap, replacementRoadmap)
  resolvedIds = resolveRoadmapIds(roadmapIdentity, replace.remap)
  context.state.sectionId = resolvedIds.sectionId
  context.state.subsectionIds = resolvedIds.subsectionIds
  context.state.itemIds = resolvedIds.itemIds
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
  assertSubsectionTags(replacedRead, resolvedIds.subsectionIds[0], ['foundations', 'arrays'])
  assertSubsectionTags(replacedRead, resolvedIds.subsectionIds[1], ['foundations', 'hashing'])
  assertSubsectionItemIds(replacedRead, resolvedIds.subsectionIds[0], resolvedIds.itemIds.slice(0, 2))
  assertSubsectionItemIds(replacedRead, resolvedIds.subsectionIds[1], [resolvedIds.itemIds[2]])
  if (replacedRead.description !== replacementRoadmap.description) {
    throw new Error('replace read-back did not persist the replacement description')
  }

  const validation = await callScenario(context, 'validate_roadmap_draft', {
    roadmap_id: create.roadmap_id,
  })
  if (!validation.publishable || validation.violations.length !== 0) {
    throw new Error('authoring fixture must validate as publishable')
  }

  const publish = await callScenario(context, 'publish_roadmap', {
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
  const metadata = await callScenario(context, 'edit_roadmap_metadata', metadataRequest)
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

  const sourceProgressUpdate = await callScenario(context, 'progress_update', {
    roadmap_id: create.roadmap_id,
    item_ids: [resolvedIds.itemIds[0]],
    state: 'complete',
  })
  const sourceProgress = await callScenario(context, 'progress_get', {
    roadmap_id: create.roadmap_id,
    detailed: true,
  })
  if (
    sourceProgress.checked_items !== 1 ||
    sourceProgress.checked_ids === null ||
    sourceProgress.checked_ids.length !== 1 ||
    sourceProgress.checked_ids[0] !== resolvedIds.itemIds[0]
  ) {
    throw new Error('source roadmap progress must contain the completed fixture item before forking')
  }

  const fork = await callScenario(context, 'fork_roadmap', {
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
  if (forkProgress.checked_items !== 0 || forkProgress.checked_ids === null || forkProgress.checked_ids.length !== 0) {
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
    sourceProgressUpdate,
    sourceProgress,
    fork,
    forkRead,
    forkProgress,
  }
}

async function readRoadmap(context: ToolJourneyContext, roadmapId: string): Promise<RoadmapOutput> {
  return callScenario(context, 'roadmap_get', { roadmap_id: roadmapId })
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
    return await callScenario(context, 'progress_get', { roadmap_id: roadmapId, detailed: true })
  } finally {
    context.state = sourceState
  }
}

function requireRevision(context: ToolJourneyContext): number {
  if (context.state.primaryRevision === null) throw new Error('authoring journey has no current roadmap revision')
  return context.state.primaryRevision
}
